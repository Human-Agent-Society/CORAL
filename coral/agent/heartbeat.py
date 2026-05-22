"""Heartbeat: registered actions with independent intervals and plateau detection."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import Any

# --- Per-trigger option schemas ---
#
# Each trigger type owns a small dataclass describing the options it accepts.
# The core ``HeartbeatAction`` carries an opaque ``options: dict[str, Any]``
# and dispatches through :func:`parse_options` so YAML typos like ``epslion``
# fail loudly at load time instead of silently being ignored.


@dataclasses.dataclass
class IntervalOptions:
    """No options for interval triggers (yet)."""


@dataclasses.dataclass
class PlateauOptions:
    """Options for ``trigger="plateau"``.

    ``epsilon`` controls what counts as "improvement" for the plateau streak.
    The streak resets only when a new score beats the prior plateau-anchor by
    at least ``epsilon`` (in the grader's ``direction``). Default 0.0
    preserves the legacy strict-> behavior. Set to your task's noise floor so
    tiny inch-ups don't keep resetting the streak.
    """

    epsilon: float = 0.0


_TRIGGER_OPTIONS: dict[str, type] = {
    "interval": IntervalOptions,
    "plateau": PlateauOptions,
}


def parse_options(trigger: str, options: dict[str, Any] | None) -> Any:
    """Parse and validate trigger-specific options against the trigger's schema.

    Raises ``ValueError`` for unknown triggers or unknown option keys, so YAML
    typos die at load instead of silently disabling a knob (the kind of bug
    that motivated ``epsilon`` in the first place).
    """
    schema = _TRIGGER_OPTIONS.get(trigger)
    if schema is None:
        raise ValueError(
            f"Unknown heartbeat trigger: {trigger!r}. Known: {sorted(_TRIGGER_OPTIONS)}"
        )
    options = options or {}
    valid_keys = {f.name for f in dataclasses.fields(schema)}
    unknown = set(options) - valid_keys
    if unknown:
        raise ValueError(
            f"Unknown options for trigger={trigger!r}: {sorted(unknown)}. "
            f"Valid keys: {sorted(valid_keys) or '(none)'}"
        )
    return schema(**options)


@dataclasses.dataclass
class HeartbeatAction:
    """A registered heartbeat action with its own interval and prompt.

    Actions trigger on a fixed interval (``trigger="interval"``) or when the
    agent's score has not improved for a number of consecutive evals
    (``trigger="plateau"``). Plateau actions use ``every`` as the stall
    threshold and include a cooldown so they don't re-fire until the agent
    improves or another ``every`` evals pass.

    Trigger-specific knobs live in ``options`` and are validated against the
    schema for ``trigger`` (see :func:`parse_options`). The core action is
    deliberately agnostic to each trigger's schema so adding a new trigger
    only requires defining its ``Options`` dataclass and registering it in
    ``_TRIGGER_OPTIONS``.
    """

    name: str  # e.g. "reflect", "consolidate", "pivot"
    every: int  # interval evals (interval) or stall threshold (plateau)
    prompt: str  # rendered prompt string
    is_global: bool = False  # True = use global eval count, False = per-agent
    trigger: str = "interval"  # "interval" or "plateau"
    options: dict[str, Any] = dataclasses.field(default_factory=dict)


def streak_for_epsilon(
    score_history: Sequence[float | None],
    *,
    minimize: bool,
    epsilon: float,
) -> int:
    """Plateau streak using an "anchor" model.

    Walks the score history left-to-right maintaining an ``anchor`` (the most
    recent score that improved over the prior anchor by at least ``epsilon``).
    The returned streak is the number of evals after the latest anchor reset.

    A score of ``None`` (e.g. grader-error attempt) counts toward the streak
    without changing the anchor — broken evals still apply plateau pressure
    *after* the anchor is set. ``None``s before the first real score are
    discarded: there is no baseline to plateau against, so the streak starts
    at 0 the moment the first real score arrives.

    Args:
        score_history: Per-eval real-mode scores in submit order. May contain
            ``None`` for evals where the grader returned no score.
        minimize: True if the grader's direction is "minimize" (lower is better).
        epsilon: Minimum delta over anchor required to reset the streak.

    Returns:
        Number of evals since the last anchor reset (0 if the latest score
        was itself an epsilon-improvement, or if the agent has no scores yet).
    """
    streak = 0
    anchor: float | None = None
    for score in score_history:
        if score is None:
            streak += 1
            continue
        if anchor is None:
            anchor = score
            streak = 0
            continue
        if minimize:
            improved = score < anchor - epsilon
        else:
            improved = score > anchor + epsilon
        if improved:
            anchor = score
            streak = 0
        else:
            streak += 1
    return streak


class HeartbeatRunner:
    """Check registered actions against eval counts and plateau state."""

    def __init__(self, actions: list[HeartbeatAction]) -> None:
        self.actions = actions
        # Track when each plateau action last fired so we don't spam
        self._plateau_fired_at: dict[str, int] = {}

    def check(
        self,
        *,
        local_eval_count: int,
        global_eval_count: int,
        score_history: Sequence[float | None] | None = None,
        minimize: bool = False,
    ) -> list[HeartbeatAction]:
        """Return all actions whose trigger condition is met.

        Args:
            local_eval_count: This agent's total eval count (real attempts only).
            global_eval_count: Total evals across all agents.
            score_history: This agent's scores in submit order. Required when
                any registered action uses ``trigger="plateau"``; ignored for
                pure interval triggers.
            minimize: True if the grader's direction is "minimize" (lower is
                better). Used by plateau triggers.
        """
        if score_history is None:
            score_history = []
        triggered = []
        for action in self.actions:
            if action.trigger == "plateau":
                opts: PlateauOptions = parse_options("plateau", action.options)
                streak = streak_for_epsilon(
                    score_history,
                    minimize=minimize,
                    epsilon=opts.epsilon,
                )
                if self._check_plateau(action, streak):
                    triggered.append(action)
            else:
                count = global_eval_count if action.is_global else local_eval_count
                if count > 0 and count % action.every == 0:
                    triggered.append(action)
        return triggered

    def _check_plateau(self, action: HeartbeatAction, streak: int) -> bool:
        """Check if a plateau action should fire given its current streak.

        Fires when ``streak >= action.every`` and enough evals have passed
        since the last time this action fired (cooldown = ``every``).
        """
        if streak < action.every:
            # Not stuck long enough — also reset cooldown when streak is fresh.
            if streak == 0:
                self._plateau_fired_at.pop(action.name, None)
            return False

        last_fired = self._plateau_fired_at.get(action.name)
        if last_fired is not None:
            # Cooldown: don't re-fire until another `every` evals of stalling.
            if streak - last_fired < action.every:
                return False

        self._plateau_fired_at[action.name] = streak
        return True
