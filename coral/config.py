"""YAML-based project configuration for CORAL, powered by OmegaConf."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from omegaconf import MISSING, OmegaConf


@dataclass
class TaskConfig:
    """Task definition within a CORAL project."""

    name: str = MISSING
    description: str = MISSING
    tips: str = ""


@dataclass
class ParallelGraderConfig:
    """Parallel evaluation in the grader daemon.

    The daemon always routes pending attempts through a worker pool of this
    size. ``max_workers=1`` (the default) is serial — same behavior as before
    the pool existed. Set higher only when the grader is concurrency-safe
    (pure Python, sandboxed swebench runs, etc.); the daemon does not enforce
    safety, so a misconfigured value with a non-safe grader is the user's
    responsibility.
    """

    max_workers: int = 1


@dataclass
class GraderConfig:
    """Grader configuration."""

    entrypoint: str = (
        ""  # "module.path:ClassName"; empty = auto-discover from eval/grader.py (deprecated)
    )
    setup: list[str] = field(
        default_factory=list
    )  # shell commands run in .coral/private/grader_venv/ before agents start
    timeout: int = 300  # eval timeout in seconds (0 = no limit)
    args: dict[str, Any] = field(default_factory=dict)
    private: list[str] = field(
        default_factory=list
    )  # files/dirs copied to .coral/ (hidden from agents)
    direction: str = "maximize"  # "maximize" or "minimize"
    # Producer-side queue cap. Reject `coral eval` when an agent already has
    # this many ungraded submissions in flight. 0 = unlimited (legacy behavior).
    # Default 1: an agent can only enqueue a fresh attempt once the prior one
    # is graded, which prevents runaway pending floods when the grader is slow.
    max_pending_per_agent: int = 1
    parallel: ParallelGraderConfig = field(default_factory=ParallelGraderConfig)

    def __post_init__(self) -> None:
        if self.max_pending_per_agent < 0:
            raise ValueError(
                f"grader.max_pending_per_agent must be >= 0, got {self.max_pending_per_agent}"
            )
        # SubprocessGrader serializes GraderConfig via dataclasses.asdict and
        # rebuilds with `GraderConfig(**payload)`, which leaves `parallel` as a
        # plain dict. Coerce here so validation and downstream attribute access
        # work for both real callers and the worker reconstruction path.
        if isinstance(self.parallel, dict):
            self.parallel = ParallelGraderConfig(**self.parallel)
        if self.parallel.max_workers < 1:
            raise ValueError(
                f"grader.parallel.max_workers must be >= 1, got {self.parallel.max_workers}"
            )


@dataclass
class HeartbeatActionConfig:
    """Configuration for a single heartbeat action.

    Trigger-specific knobs (e.g. ``epsilon`` for plateau) go under
    ``options``. The schema is validated at runtime against the trigger; see
    :class:`coral.agent.heartbeat.PlateauOptions`.
    """

    name: str = MISSING  # e.g. "reflect", "consolidate", "pivot"
    every: int = MISSING  # trigger every N evals (interval) or stall threshold (plateau)
    is_global: bool = False  # True = use global eval count, False = per-agent
    trigger: str = "interval"  # "interval" or "plateau"
    prompt: str = ""  # custom prompt; if empty, falls back to built-in DEFAULT_PROMPTS
    # Trigger-specific options. For ``trigger="plateau"`` the recognized key
    # is ``epsilon`` (minimum delta over the prior plateau-anchor that counts
    # as improvement; default 0.0 = legacy strict-> behavior). Unknown keys
    # raise at load time.
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class GatewayConfig:
    """LiteLLM gateway configuration for intercepting agent model traffic."""

    enabled: bool = False
    port: int = 4000
    config: str = ""  # path to litellm_config.yaml
    api_key: str = ""  # LiteLLM master key (auto-generated if empty)


@dataclass
class WarmStartConfig:
    """Warm-start configuration: optional research phase before the main coding loop."""

    enabled: bool = False


@dataclass
class AgentAssignmentConfig:
    """Per-assignment override of runtime/model for mix-and-match multi-agent runs.

    When ``agents.assignments`` is set, it overrides ``agents.count``: the total
    number of agents spawned is the sum of ``count`` across every assignment.
    Empty string fields inherit from the top-level ``agents.*`` defaults.
    Each assignment can override:
    - ``runtime``:        the agent runtime (claude_code / codex / opencode / ...)
    - ``model``:          model passed to that runtime
    - ``count``:          how many agents of this kind to spawn (default 1)
    - ``runtime_options`` extra options forwarded to that runtime's ``start()``
    """

    runtime: str = ""  # empty -> inherit from agents.runtime
    model: str = ""  # empty -> inherit from agents.model (or runtime default)
    count: int = 1
    runtime_options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError(f"agents.assignments[].count must be >= 1, got {self.count}")


@dataclass
class AgentConfig:
    """Agent spawning configuration."""

    count: int = 1
    runtime: str = "claude_code"
    model: str = "sonnet"
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    warmstart: WarmStartConfig = field(default_factory=WarmStartConfig)
    runtime_options: dict[str, Any] = field(default_factory=dict)
    # Mix-and-match: when non-empty, each entry spawns its own runtime/model
    # combo. ``agents.count`` is ignored (total = sum of assignment counts).
    # Empty fields on an assignment inherit the agents.* defaults below.
    assignments: list[AgentAssignmentConfig] = field(default_factory=list)
    max_turns: int = 200
    # Stall watchdog: restart an agent that produces no output for this many
    # seconds. 0 disables the watchdog. Default 1200s (20 min) catches deadlocks
    # faster than the prior 3600s while still being well above legitimate quiet
    # periods (long tool calls, grader queue waits — the latter is exempted).
    timeout: int = 1200
    heartbeat: list[HeartbeatActionConfig] = field(
        default_factory=lambda: [
            HeartbeatActionConfig(name="reflect", every=1),
            HeartbeatActionConfig(name="consolidate", every=10, is_global=True),
            HeartbeatActionConfig(name="pivot", every=5, trigger="plateau"),
            HeartbeatActionConfig(name="lint_wiki", every=10, is_global=True),
        ]
    )
    skills: list[str] = field(default_factory=list)  # skill dirs copied to .coral/public/skills/
    research: bool = True  # enable web search / literature review step in workflow
    stagger_seconds: int = 0  # delay between spawning each agent (rate-limit backpressure)

    # Reliability: crash-burst circuit breaker.
    # When an agent exits repeatedly in a short window with no clean-exit marker,
    # the manager pauses it instead of respawning into a tight loop.
    # 0 in any of the three knobs disables the breaker entirely.
    restart_burst_threshold: int = 3  # crashes within window before pausing the agent
    restart_burst_window: int = 30  # seconds; sliding window for crash counting
    restart_pause_seconds: int = (
        300  # how long the paused state holds before restart attempts resume
    )

    # Reliability: grader-queue exemption for stall detection.
    # Skip stall checks for an agent whose latest attempt is pending grading,
    # but only if the grader process is alive and the pending attempt is not stale.
    grader_pending_max_age: int = 1800  # seconds; older pending attempts no longer exempt

    # Reliability: minimum runtime in seconds before an exit_code==0 is considered "clean"
    # for runtimes that lack a stable terminal marker (codex/opencode/kiro).
    min_clean_runtime_seconds: int = 60

    def __post_init__(self) -> None:
        # Reject negative values for the new reliability knobs;
        # 0 is treated as "disabled" for the same fields where it makes sense.
        for field_name in (
            "restart_burst_threshold",
            "restart_burst_window",
            "restart_pause_seconds",
            "grader_pending_max_age",
            "min_clean_runtime_seconds",
        ):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(f"agents.{field_name} must be >= 0, got {value}")
        # If the breaker is enabled at all, the pause must outlast the burst window;
        # otherwise the breaker can re-arm before the burst counter has cleared.
        if (
            self.restart_burst_threshold > 0
            and self.restart_burst_window > 0
            and 0 < self.restart_pause_seconds < self.restart_burst_window
        ):
            raise ValueError(
                "agents.restart_pause_seconds must be >= agents.restart_burst_window "
                f"(got pause={self.restart_pause_seconds}, window={self.restart_burst_window})"
            )

    def heartbeat_interval(self, name: str) -> int:
        """Get the interval for a heartbeat action by name."""
        for action in self.heartbeat:
            if action.name == name:
                return action.every
        raise KeyError(f"No heartbeat action named {name!r}")


@dataclass
class SharingConfig:
    """What shared state is enabled."""

    attempts: bool = True
    notes: bool = True
    skills: bool = True


@dataclass
class WorkspaceConfig:
    """Workspace layout configuration."""

    results_dir: str = "./results"
    repo_path: str = "."
    setup: list[str] = field(default_factory=list)  # shell commands to run before agents start
    # Ignored if results_dir is set
    base_dir: str = ""
    run_dir: str = ""  # if set, use this exact run directory instead of generating one


@dataclass
class RunConfig:
    """Runtime flags for a CORAL session."""

    verbose: bool = False
    ui: bool = False
    session: str = "tmux"  # "local", "tmux", or "docker"
    docker_image: str = ""  # empty = auto-build from project Dockerfile


@dataclass
class CoralConfig:
    """Top-level project configuration."""

    task: TaskConfig = field(default_factory=TaskConfig)
    grader: GraderConfig = field(default_factory=GraderConfig)
    agents: AgentConfig = field(default_factory=AgentConfig)
    sharing: SharingConfig = field(default_factory=SharingConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    run: RunConfig = field(default_factory=RunConfig)
    task_dir: Path | None = None  # internal: directory containing task.yaml

    @classmethod
    def from_yaml(cls, path: str | Path) -> CoralConfig:
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CoralConfig:
        data = _preprocess(dict(data))
        schema = OmegaConf.structured(cls)
        raw = OmegaConf.create(data)
        merged = OmegaConf.merge(schema, raw)
        cfg: CoralConfig = OmegaConf.to_object(merged)  # type: ignore[assignment]
        return cfg

    def to_dict(self) -> dict[str, Any]:
        sc = OmegaConf.structured(self)
        container: dict[str, Any] = OmegaConf.to_container(sc, resolve=True)  # type: ignore[assignment]
        # Remove internal-only fields
        container.pop("task_dir", None)
        # Serialize heartbeat is_global as "global" for YAML compat
        for h in container.get("agents", {}).get("heartbeat", []):
            h["global"] = h.pop("is_global", False)
        return container

    def to_yaml(self, path: str | Path) -> None:
        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)

    @classmethod
    def merge_dotlist(cls, config: CoralConfig, dotlist: list[str]) -> CoralConfig:
        """Merge CLI dotlist overrides into an existing config."""
        if not dotlist:
            return config
        base = OmegaConf.structured(config)
        overrides = OmegaConf.from_dotlist(dotlist)
        merged = OmegaConf.merge(base, overrides)
        cfg: CoralConfig = OmegaConf.to_object(merged)  # type: ignore[assignment]
        return cfg


def _preprocess(data: dict[str, Any]) -> dict[str, Any]:
    """Transform legacy keys and normalize heartbeat config before OmegaConf merge."""
    # Reject removed grader.type / grader.module fields with migration guidance.
    grader_data = data.get("grader")
    if isinstance(grader_data, dict):
        legacy_grader_keys = [k for k in ("type", "module") if k in grader_data]
        if legacy_grader_keys:
            raise ValueError(
                f"grader.{' / grader.'.join(legacy_grader_keys)} is removed. "
                f"Use grader.entrypoint = 'your_pkg.module:Grader' (and grader.setup "
                f"to install the package). See docs/guides/custom-grader."
            )

    agents_data = data.get("agents", {})
    if not isinstance(agents_data, dict):
        return data

    # Make a copy so we don't mutate the original
    agents_data = dict(agents_data)

    heartbeat_raw = agents_data.pop("heartbeat", None)
    old_reflect = agents_data.pop("reflect_every", None)
    old_heartbeat = agents_data.pop("heartbeat_every", None)

    if heartbeat_raw is not None:
        specified = {h["name"] for h in heartbeat_raw}
        for dflt in AgentConfig().heartbeat:
            if dflt.name not in specified:
                heartbeat_raw.append(
                    {
                        "name": dflt.name,
                        "every": dflt.every,
                        "global": dflt.is_global,
                        "trigger": dflt.trigger,
                    }
                )
        agents_data["heartbeat"] = [
            {
                "name": h["name"],
                "every": h["every"],
                "is_global": h.get("global", False),
                "trigger": h.get("trigger", "interval"),
                "prompt": h.get("prompt", ""),
            }
            for h in heartbeat_raw
        ]
    elif old_reflect is not None or old_heartbeat is not None:
        agents_data["heartbeat"] = [
            {
                "name": "reflect",
                "every": old_reflect if old_reflect is not None else 1,
                "is_global": False,
            },
            {
                "name": "consolidate",
                "every": old_heartbeat if old_heartbeat is not None else 10,
                "is_global": False,
            },
        ]

    # If runtime is set but model is not, use the runtime-specific default.
    # Custom-entrypoint runtimes ('module.path:ClassName') have no default —
    # require the user to set agents.model explicitly so a footgun like the
    # builtin "sonnet" default doesn't silently land on a foreign runtime.
    if "runtime" in agents_data and "model" not in agents_data:
        from coral.agent.registry import default_model_for_runtime

        rt = agents_data["runtime"]
        default_model = default_model_for_runtime(rt)
        if default_model:
            agents_data["model"] = default_model
        elif isinstance(rt, str) and ":" in rt:
            raise ValueError(
                f"agents.runtime={rt!r} is a custom runtime entrypoint; "
                f"set agents.model explicitly in task.yaml."
            )

    # Normalize assignments: fill in missing model defaults from the assignment's
    # runtime so each entry stores a concrete model. Empty fields are kept as ""
    # (will inherit from the top-level agents.* defaults at resolve time).
    assignments_raw = agents_data.get("assignments")
    if isinstance(assignments_raw, list):
        from coral.agent.registry import default_model_for_runtime

        normalized: list[dict[str, Any]] = []
        for entry in assignments_raw:
            if not isinstance(entry, dict):
                continue
            entry = dict(entry)
            if entry.get("runtime") and not entry.get("model"):
                m = default_model_for_runtime(entry["runtime"])
                if m:
                    entry["model"] = m
            normalized.append(entry)
        agents_data["assignments"] = normalized

    data["agents"] = agents_data

    # Remove task_dir if present in raw data (it's internal-only)
    data.pop("task_dir", None)

    return data
