"""Remote agent runtime contracts and state bridge helpers."""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class RemoteAgentSpec:
    """Description of an agent CORAL wants a remote runtime to deploy."""

    agent_id: str
    name: str
    code_path: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["code_path"] = str(self.code_path) if self.code_path else None
        return data


@dataclass(frozen=True)
class RemoteAgentHandle:
    """Stable pointer to an agent managed by a remote runtime."""

    agent_id: str
    runtime_type: str
    runtime_id: str
    endpoint: str | None = None
    status: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RemoteAgentState:
    """Normalized state collected from a remote runtime."""

    agent_id: str
    runtime_type: str
    runtime_id: str
    status: str
    collected_at: str = field(default_factory=utc_now_iso)
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@runtime_checkable
class RemoteRuntime(Protocol):
    """Protocol for agents that run outside CORAL-managed local worktrees."""

    runtime_type: str

    def deploy(self, agent_spec: RemoteAgentSpec) -> RemoteAgentHandle:
        """Deploy or bind a remote agent and return its handle."""

    def invoke(self, handle: RemoteAgentHandle, payload: dict[str, Any]) -> dict[str, Any]:
        """Invoke a remote agent."""

    def list_agents(self) -> list[RemoteAgentHandle]:
        """Return known remote agents."""

    def collect_metrics(self) -> list[RemoteAgentState]:
        """Return normalized state for known remote agents."""


def load_remote_runtime(class_path: str, config: dict[str, Any] | None = None) -> RemoteRuntime:
    """Load a remote runtime adapter from ``module:Class`` notation."""
    if class_path.count(":") != 1:
        raise ValueError(
            f"Remote runtime class must be 'module.path:ClassName', got {class_path!r}"
        )
    module_name, class_name = class_path.split(":", 1)
    if not module_name or not class_name:
        raise ValueError(
            f"Remote runtime class must be 'module.path:ClassName', got {class_path!r}"
        )

    module = importlib.import_module(module_name)
    runtime_class = getattr(module, class_name)
    runtime_config = config or {}
    from_config = getattr(runtime_class, "from_config", None)
    runtime = (
        from_config(runtime_config) if callable(from_config) else runtime_class(**runtime_config)
    )
    if not isinstance(runtime, RemoteRuntime):
        raise TypeError(
            f"{class_path} does not satisfy the RemoteRuntime protocol "
            "(see coral/agent/remote.py for the required methods)."
        )
    return runtime


class RemoteStateBridge:
    """Persist remote runtime state under ``.coral/public/remote_state``."""

    def __init__(self, runtime: RemoteRuntime, state_dir: Path) -> None:
        self.runtime = runtime
        self.state_dir = state_dir

    def sync_once(self) -> list[RemoteAgentState]:
        """Collect metrics once and atomically write state files."""
        states = self.runtime.collect_metrics()
        serialized = [state.to_dict() for state in states]
        self.state_dir.mkdir(parents=True, exist_ok=True)

        for state in serialized:
            self._write_json(self.state_dir / self._state_filename(state["agent_id"]), state)

        self._write_json(
            self.state_dir / "index.json",
            {
                "runtime_type": self.runtime.runtime_type,
                "collected_at": utc_now_iso(),
                "agents": serialized,
            },
        )
        return states

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp_path, path)

    @staticmethod
    def _state_filename(agent_id: Any) -> str:
        encoded = quote(str(agent_id), safe="")
        return f"{encoded or '_'}.json"


def read_remote_state(coral_dir: str | Path) -> dict[str, Any] | None:
    """Best-effort read of the remote state index for CLI and web status."""
    path = Path(coral_dir) / "public" / "remote_state" / "index.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
