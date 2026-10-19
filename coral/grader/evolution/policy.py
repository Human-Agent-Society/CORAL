"""Evolution policy: the arm, the checkpoint schedule, and the slot budget.

The rubric changes only at fixed checkpoints on the scored-observation clock. The
trajectory decides *whether and what* changes at a checkpoint; it never decides
*when*. Score-only triggers (variance, plateau, "everyone passes") measure how
much the agent population happens to vary, not whether the rubric still
discriminates; on the same task they fired too early against weak builders and
too late against strong ones. Fixed checkpoints remove the timing question so
only the content question remains: shown the trajectory, does the proposer find
something a reader would agree is missing?

Checkpoints are indices on the SCORED-observation clock. An evaluation that
failed for infrastructure reasons is not an observation and does not advance a
checkpoint, so a proposer is never invoked because failures consumed its
evidence window. Submissions and failures are counted and recorded separately;
the yoked arm replays the same scored indices. ``latest_publication_attempt``
alone is a bound on the real-attempt clock, because it protects exposure, which
is a matter of attempts left in the budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from coral.grader.evolution.state import RubricSnapshot

MODES = ("static", "adaptive", "yoked")

#: Keys from earlier protocol generations (variance triggers, warm-up/cool-down
#: gates, probation and retirement). Refused rather than ignored, so an old
#: task file cannot silently run a different protocol.
_REMOVED_KEYS = (
    "warmup_attempts",
    "cooldown_attempts",
    "max_updates",
    "triggers",
    "retirement_enabled",
    "variance_threshold",
    "correlation_threshold",
)


@dataclass
class PolicyConfig:
    #: ``static`` never changes the rubric. ``adaptive`` invokes the proposer at
    #: each checkpoint with the trajectory as evidence. ``yoked`` replays a paired
    #: adaptive run's checkpoint outcomes (same points, same counts) with a
    #: proposer that sees only the task brief, never the trajectory.
    mode: str = "static"

    #: Scored-observation indices at which the proposer is invoked. Required for
    #: the adaptive arm; the yoked arm takes its schedule from the exported file.
    #: Positive, unique, strictly increasing.
    checkpoints: list[int] = field(default_factory=list)

    #: Hard cap on rubric size. A checkpoint with no free slot is recorded as
    #: ``blocked``, never as an abstention.
    max_criteria: int = 11

    #: Last real-attempt index at which a publication may happen. A criterion
    #: published with no later attempt to be scored against it inflates the
    #: publication count without any exposure; this refuses it. None disables.
    latest_publication_attempt: int | None = None

    #: How many recent SCORED observations of the current version the proposer
    #: is shown, i.e. how far back the evidence window reaches from the checkpoint.
    window: int = 5

    #: Cap on criteria admitted per checkpoint.
    max_new_criteria_per_round: int = 2

    #: Whether agents' shared notes are staged as proposer evidence, and how
    #: many characters of them.
    agent_notes_enabled: bool = True
    agent_notes_char_budget: int = 4000

    #: Evaluator retries on infrastructure failure before an attempt is recorded
    #: as failed (never as an observation).
    max_evaluation_retries: int = 1

    #: The proposer is a different role from the online evaluator; keep it a
    #: separate knob. None falls back to ``evaluator_model``.
    proposer_model: str | None = None
    proposer_timeout: int = 600
    #: Which proposer backend runs the call (``proposals.PROPOSER_BACKENDS``).
    proposer_runtime: str = "claude_code"
    #: Optional replacement for the ``claude`` CLI: a command that reads the
    #: prompt on stdin, runs in the staged evidence directory, and prints the
    #: proposal JSON. For the offline demo and tests; a study run leaves it unset.
    proposer_command: list[str] | None = None

    #: Weight given to every admitted criterion. Proposal-supplied weights are
    #: ignored so arms differ in what criteria say, not in how much they count.
    expansion_weight: float = 1.0

    @classmethod
    def from_args(cls, cfg: dict[str, Any] | None) -> PolicyConfig:
        cfg = cfg or {}
        legacy = sorted(k for k in _REMOVED_KEYS if k in cfg)
        if legacy:
            raise ValueError(
                f"evolution config keys {legacy} belong to a removed protocol generation "
                "(variance triggers, gates, probation/retirement); evolution is "
                "checkpoint-scheduled. Remove them."
            )
        mode = str(cfg.get("mode", "static")).strip().lower()
        if mode not in MODES:
            raise ValueError(f"evolution.mode must be one of {MODES}; got {mode!r}")
        checkpoints = [int(c) for c in (cfg.get("checkpoints") or [])]
        if checkpoints:
            if any(c <= 0 for c in checkpoints):
                raise ValueError(f"evolution.checkpoints must all be positive; got {checkpoints}")
            if len(set(checkpoints)) != len(checkpoints):
                raise ValueError(f"evolution.checkpoints must be unique; got {checkpoints}")
            if checkpoints != sorted(checkpoints):
                raise ValueError(
                    f"evolution.checkpoints must be strictly increasing; got {checkpoints}"
                )
        if mode == "adaptive" and not checkpoints:
            raise ValueError("evolution.mode is adaptive but evolution.checkpoints is empty")
        command = cfg.get("proposer_command")
        if command is not None and (
            not isinstance(command, list) or not all(isinstance(x, str) for x in command)
        ):
            raise ValueError("evolution.proposer_command must be a list of strings")
        return cls(
            mode=mode,
            checkpoints=checkpoints,
            max_criteria=int(cfg.get("max_criteria", 11)),
            latest_publication_attempt=(
                None
                if cfg.get("latest_publication_attempt") is None
                else int(cfg["latest_publication_attempt"])
            ),
            window=int(cfg.get("window", 5)),
            max_new_criteria_per_round=int(cfg.get("max_new_criteria_per_round", 2)),
            agent_notes_enabled=bool(cfg.get("agent_notes_enabled", True)),
            agent_notes_char_budget=int(cfg.get("agent_notes_char_budget", 4000)),
            max_evaluation_retries=int(cfg.get("max_evaluation_retries", 1)),
            proposer_model=(
                str(cfg["proposer_model"]) if cfg.get("proposer_model") is not None else None
            ),
            proposer_timeout=int(cfg.get("proposer_timeout", 600)),
            proposer_runtime=str(cfg.get("proposer_runtime", "claude_code")),
            proposer_command=list(command) if command is not None else None,
            expansion_weight=float(cfg.get("expansion_weight", 1.0)),
        )


@dataclass
class Gate:
    """Whether publication is permitted now, and how many criteria could be added."""

    allowed: bool
    reason: str
    free_slots: int
    blockers: list[str] = field(default_factory=list)


@dataclass
class TriggerResult:
    """What caused this evaluation of the rubric: the checkpoint's name and the
    attempt ids whose feedback the proposer will be shown."""

    fired: str | None
    detail: str
    attempt_ids: list[str] = field(default_factory=list)


def free_slots(snap: RubricSnapshot, cfg: PolicyConfig) -> int:
    return max(0, cfg.max_criteria - len(snap.criteria))


def checkpoint_due(scored: int, checkpoints: list[int], evaluated: int) -> tuple[int | None, str]:
    """The next checkpoint to evaluate, if the scored-observation count has reached it.

    ``evaluated`` is how many checkpoints this arm has already looked at,
    whatever their outcome; each checkpoint is evaluated exactly once, when the
    observation count first reaches it.
    """
    if evaluated >= len(checkpoints):
        return None, f"all {len(checkpoints)} checkpoints evaluated"
    target = checkpoints[evaluated]
    if scored < target:
        return None, f"{scored} scored observations; next checkpoint at {target}"
    return target, f"checkpoint {target} reached ({scored} scored observations)"
