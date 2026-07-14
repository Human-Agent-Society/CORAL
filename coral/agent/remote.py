"""Contracts and helpers for remote agent adapters."""

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
class RemoteWorkspaceGrant:
    """Explicit authority CORAL grants to a remote runtime for one agent."""

    grant_id: str
    issuer: str
    workspace_id: str
    permitted_operations: list[str] = field(default_factory=list)
    memory_namespace: str | None = None
    artifact_namespace: str | None = None
    expires_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RemoteAgentSpec:
    """Description of an agent CORAL wants a remote runtime to deploy or bind."""

    agent_id: str
    name: str
    code_path: Path | None = None
    grant: RemoteWorkspaceGrant | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "agent_id": self.agent_id,
            "name": self.name,
            "code_path": str(self.code_path) if self.code_path else None,
            "grant": self.grant.to_dict() if self.grant else None,
            "metadata": dict(self.metadata),
        }
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
class RemoteEvidence:
    """Typed evidence imported from a remote runtime.

    CORAL treats remote evidence as observations. Graders decide which
    evidence, if any, is trusted for scoring or completion.
    """

    artifact_id: str
    kind: str
    source_runtime: str
    runtime_id: str
    collected_at: str = field(default_factory=utc_now_iso)
    digest: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    trust_level: str = "observed"
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
    evidence: list[RemoteEvidence] = field(default_factory=list)
    recovery: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = [item.to_dict() for item in self.evidence]
        return data


@runtime_checkable
class RemoteRuntimeAdapter(Protocol):
    """Adapter for agents that run outside CORAL-managed local worktrees."""

    runtime_type: str

    def deploy(self, agent_spec: RemoteAgentSpec) -> RemoteAgentHandle:
        """Deploy or bind a remote agent and return its handle."""

    def invoke(self, handle: RemoteAgentHandle, payload: dict[str, Any]) -> dict[str, Any]:
        """Start or resume useful remote work for an agent."""

    def list_agents(self) -> list[RemoteAgentHandle]:
        """Return known remote agents."""

    def collect_metrics(self) -> list[RemoteAgentState]:
        """Return normalized state for known remote agents."""


def load_remote_adapter(
    class_path: str, config: dict[str, Any] | None = None
) -> RemoteRuntimeAdapter:
    """Load a remote adapter from ``module.path:ClassName`` notation."""
    if class_path.count(":") != 1:
        raise ValueError(f"Remote adapter must be 'module.path:ClassName', got {class_path!r}")
    module_name, class_name = class_path.split(":", 1)
    if not module_name or not class_name:
        raise ValueError(f"Remote adapter must be 'module.path:ClassName', got {class_path!r}")

    module = importlib.import_module(module_name)
    adapter_class = getattr(module, class_name)
    adapter_config = config or {}
    from_config = getattr(adapter_class, "from_config", None)
    adapter = (
        from_config(adapter_config) if callable(from_config) else adapter_class(**adapter_config)
    )
    if not isinstance(adapter, RemoteRuntimeAdapter):
        raise TypeError(
            f"{class_path} does not satisfy the RemoteRuntimeAdapter protocol "
            "(see coral/agent/remote.py for the required methods)."
        )
    return adapter


class RemoteStateBridge:
    """Persist remote runtime state under ``.coral/public/remote_state``."""

    def __init__(self, adapter: RemoteRuntimeAdapter, state_dir: Path) -> None:
        self.adapter = adapter
        self.state_dir = state_dir

    def sync_once(self) -> list[RemoteAgentState]:
        """Collect metrics once and atomically write per-agent state files."""
        states = self.adapter.collect_metrics()
        self.write_states(states)
        return states

    def write_states(self, states: list[RemoteAgentState]) -> None:
        """Atomically write normalized per-agent state files.

        The aggregate index is generated by ``read_remote_state`` from these
        per-agent files so multiple proxy workers do not overwrite each other.
        """
        serialized = [state.to_dict() for state in states]
        self.state_dir.mkdir(parents=True, exist_ok=True)

        for state in serialized:
            self._write_json(self.state_dir / self._state_filename(state["agent_id"]), state)

    @staticmethod
    def _state_filename(agent_id: Any) -> str:
        encoded = quote(str(agent_id), safe="")
        return f"{encoded or '_'}.json"

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp_path, path)


def read_remote_state(coral_dir: str | Path) -> dict[str, Any] | None:
    """Best-effort read of remote state for CLI and web status."""
    state_dir = Path(coral_dir) / "public" / "remote_state"
    if not state_dir.exists():
        return None

    agents: list[dict[str, Any]] = []
    for path in sorted(state_dir.glob("*.json")):
        if path.name == "index.json" or path.name.endswith(".tmp"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("agent_id"), str):
            agents.append(payload)

    if agents:
        runtime_types = sorted(
            {
                agent["runtime_type"]
                for agent in agents
                if isinstance(agent.get("runtime_type"), str)
            }
        )
        return {
            "runtime_type": runtime_types[0] if len(runtime_types) == 1 else "mixed",
            "runtime_types": runtime_types,
            "collected_at": utc_now_iso(),
            "agents": agents,
        }

    index_path = state_dir / "index.json"
    if not index_path.exists():
        return None
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
