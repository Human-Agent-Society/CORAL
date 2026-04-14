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
class GraderConfig:
    """Grader configuration."""

    type: str = ""  # if empty, auto-discovers from eval/grader.py
    module: str = ""  # Python module path for custom graders
    timeout: int = 300  # eval timeout in seconds (0 = no limit)
    args: dict[str, Any] = field(default_factory=dict)
    private: list[str] = field(
        default_factory=list
    )  # files/dirs copied to .coral/ (hidden from agents)
    direction: str = "maximize"  # "maximize" or "minimize"


@dataclass
class HeartbeatActionConfig:
    """Configuration for a single heartbeat action."""

    name: str = MISSING  # e.g. "reflect", "consolidate", "pivot"
    every: int = MISSING  # trigger every N evals (interval) or stall threshold (plateau)
    is_global: bool = False  # True = use global eval count, False = per-agent
    trigger: str = "interval"  # "interval" or "plateau"


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
class AgentConfig:
    """Agent spawning configuration."""

    count: int = 1
    runtime: str = "claude_code"
    model: str = "sonnet"
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    warmstart: WarmStartConfig = field(default_factory=WarmStartConfig)
    runtime_options: dict[str, Any] = field(default_factory=dict)
    max_turns: int = 200
    timeout: int = 3600
    heartbeat: list[HeartbeatActionConfig] = field(
        default_factory=lambda: [
            HeartbeatActionConfig(name="reflect", every=1),
            HeartbeatActionConfig(name="consolidate", every=10, is_global=True),
            HeartbeatActionConfig(name="pivot", every=5, trigger="plateau"),
            HeartbeatActionConfig(name="lint_wiki", every=10, is_global=True),
        ]
    )
    research: bool = True  # enable web search / literature review step in workflow
    stagger_seconds: int = 0  # delay between spawning each agent (rate-limit backpressure)

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
    agents_data = data.get("agents", {})
    if not isinstance(agents_data, dict):
        return data

    # Make a copy so we don't mutate the original
    agents_data = dict(agents_data)

    heartbeat_raw = agents_data.pop("heartbeat", None)
    old_reflect = agents_data.pop("reflect_every", None)
    old_heartbeat = agents_data.pop("heartbeat_every", None)

    if heartbeat_raw is not None:
        agents_data["heartbeat"] = [
            {
                "name": h["name"],
                "every": h["every"],
                "is_global": h.get("global", False),
                "trigger": h.get("trigger", "interval"),
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

    # If runtime is set but model is not, use the runtime-specific default
    if "runtime" in agents_data and "model" not in agents_data:
        from coral.agent.registry import default_model_for_runtime

        default_model = default_model_for_runtime(agents_data["runtime"])
        if default_model:
            agents_data["model"] = default_model

    data["agents"] = agents_data

    # Remove task_dir if present in raw data (it's internal-only)
    data.pop("task_dir", None)

    return data
