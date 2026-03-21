"""YAML-based project configuration for CORAL."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class TaskConfig:
    """Task definition within a CORAL project."""

    name: str
    description: str
    files: list[str] = field(default_factory=list)
    tips: str = ""
    seed: list[str] = field(default_factory=list)  # files/dirs to copy into workspace


@dataclass
class GraderConfig:
    """Grader configuration."""

    type: str = ""  # if empty, auto-discovers from eval/grader.py
    module: str = ""  # Python module path for custom graders
    timeout: int = 300  # eval timeout in seconds (0 = no limit)
    args: dict[str, Any] = field(default_factory=dict)
    private: list[str] = field(default_factory=list)  # files/dirs copied to .coral/ (hidden from agents)
    direction: str = "maximize"  # "maximize" or "minimize"


@dataclass
class HeartbeatActionConfig:
    """Configuration for a single heartbeat action."""

    name: str  # e.g. "reflect", "consolidate"
    every: int  # trigger every N evals (must be >= 1)
    is_global: bool = False  # True = use global eval count, False = per-agent


@dataclass
class AgentConfig:
    """Agent spawning configuration."""

    count: int = 1
    runtime: str = "claude_code"
    model: str = "sonnet"
    runtime_options: dict[str, Any] = field(default_factory=dict)
    max_turns: int = 200
    timeout: int = 3600
    heartbeat: list[HeartbeatActionConfig] = field(default_factory=lambda: [
        HeartbeatActionConfig(name="reflect", every=1),
        HeartbeatActionConfig(name="consolidate", every=10, is_global=True),
    ])
    research: bool = True  # enable web search / literature review step in workflow

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
    # Ignored if results_dir is set
    base_dir: str = ""


@dataclass
class CoralConfig:
    """Top-level project configuration."""

    task: TaskConfig
    grader: GraderConfig = field(default_factory=GraderConfig)
    agents: AgentConfig = field(default_factory=AgentConfig)
    sharing: SharingConfig = field(default_factory=SharingConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    task_dir: Path | None = None  # internal: directory containing task.yaml

    @classmethod
    def from_yaml(cls, path: str | Path) -> CoralConfig:
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CoralConfig:
        task_data = data["task"]
        task = TaskConfig(
            name=task_data["name"],
            description=task_data["description"],
            files=task_data.get("files", []),
            tips=task_data.get("tips", ""),
            seed=task_data.get("seed", []),
        )
        grader_data = data.get("grader", {})
        grader = GraderConfig(
            type=grader_data.get("type", ""),
            module=grader_data.get("module", ""),
            timeout=grader_data.get("timeout", 300),
            args=grader_data.get("args", {}),
            private=grader_data.get("private", []),
            direction=grader_data.get("direction", "maximize"),
        )
        agents_data = data.get("agents", {})
        heartbeat_raw = agents_data.pop("heartbeat", None)
        # Convert reflect_every/heartbeat_every to heartbeat list
        old_reflect = agents_data.pop("reflect_every", None)
        old_heartbeat = agents_data.pop("heartbeat_every", None)
        if heartbeat_raw is not None:
            heartbeat = [
                HeartbeatActionConfig(
                    name=h["name"], every=h["every"],
                    is_global=h.get("global", False),
                )
                for h in heartbeat_raw
            ]
        elif old_reflect is not None or old_heartbeat is not None:
            heartbeat = [
                HeartbeatActionConfig(name="reflect", every=old_reflect if old_reflect is not None else 1),
                HeartbeatActionConfig(name="consolidate", every=old_heartbeat if old_heartbeat is not None else 10),
            ]
        else:
            heartbeat = None  # use dataclass default

        if heartbeat is not None:
            agents_data["heartbeat"] = heartbeat
        # If runtime is set but model is not, use the runtime-specific default
        if "runtime" in agents_data and "model" not in agents_data:
            from coral.agent.registry import default_model_for_runtime
            default_model = default_model_for_runtime(agents_data["runtime"])
            if default_model:
                agents_data["model"] = default_model
        agents = AgentConfig(**agents_data)
        sharing = SharingConfig(**data.get("sharing", {}))

        ws_data = data.get("workspace", {})
        workspace = WorkspaceConfig(
            results_dir=ws_data.get("results_dir", "./results"),
            repo_path=ws_data.get("repo_path", "."),
            base_dir=ws_data.get("base_dir", ""),
        )
        return cls(
            task=task,
            grader=grader,
            agents=agents,
            sharing=sharing,
            workspace=workspace,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": {
                "name": self.task.name,
                "description": self.task.description,
                "files": self.task.files,
                "tips": self.task.tips,
                "seed": self.task.seed,
            },
            "grader": {
                "type": self.grader.type,
                "module": self.grader.module,
                "timeout": self.grader.timeout,
                "args": self.grader.args,
                "private": self.grader.private,
                "direction": self.grader.direction,
            },
            "agents": {
                "count": self.agents.count,
                "runtime": self.agents.runtime,
                "model": self.agents.model,
                "runtime_options": self.agents.runtime_options,
                "max_turns": self.agents.max_turns,
                "timeout": self.agents.timeout,
                "heartbeat": [
                    {"name": h.name, "every": h.every, "global": h.is_global}
                    for h in self.agents.heartbeat
                ],
                "research": self.agents.research,
            },
            "sharing": {
                "attempts": self.sharing.attempts,
                "notes": self.sharing.notes,
                "skills": self.sharing.skills,
            },
            "workspace": {
                "results_dir": self.workspace.results_dir,
                "repo_path": self.workspace.repo_path,
            },
        }

    def to_yaml(self, path: str | Path) -> None:
        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)
