"""Remote adapter contracts and state bridge."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from coral.agent.remote import (
    RemoteAgentHandle,
    RemoteAgentSpec,
    RemoteAgentState,
    RemoteStateBridge,
    load_remote_adapter,
    read_remote_state,
)


class _FakeRemoteAdapter:
    runtime_type = "fake"

    def __init__(self, prefix: str = "agent") -> None:
        self.prefix = prefix

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> _FakeRemoteAdapter:
        return cls(prefix=str(config.get("prefix", "agent")))

    def deploy(self, agent_spec: RemoteAgentSpec) -> RemoteAgentHandle:
        return RemoteAgentHandle(
            agent_id=agent_spec.agent_id,
            runtime_type=self.runtime_type,
            runtime_id=f"remote-{agent_spec.agent_id}",
        )

    def invoke(self, handle: RemoteAgentHandle, payload: dict[str, Any]) -> dict[str, Any]:
        return {"runtime_id": handle.runtime_id, "payload": payload}

    def list_agents(self) -> list[RemoteAgentHandle]:
        return [
            RemoteAgentHandle(
                agent_id=f"{self.prefix}-1",
                runtime_type=self.runtime_type,
                runtime_id="remote-1",
                status="running",
            )
        ]

    def collect_metrics(self) -> list[RemoteAgentState]:
        return [
            RemoteAgentState(
                agent_id=f"{self.prefix}-1",
                runtime_type=self.runtime_type,
                runtime_id="remote-1",
                status="running",
                metrics={"score": 0.42},
                artifacts={"trace": "trace-1"},
            )
        ]


class _UnsafeIdRemoteAdapter(_FakeRemoteAdapter):
    def collect_metrics(self) -> list[RemoteAgentState]:
        return [
            RemoteAgentState(
                agent_id="../remote/agent",
                runtime_type=self.runtime_type,
                runtime_id="remote-unsafe",
                status="running",
            )
        ]


class _NotRemoteAdapter:
    runtime_type = "fake"


@pytest.fixture
def fake_remote_module() -> types.ModuleType:
    mod_name = "coral_test_fake_remote_adapter"
    module = types.ModuleType(mod_name)
    module.FakeRemoteAdapter = _FakeRemoteAdapter  # type: ignore[attr-defined]
    module.NotRemoteAdapter = _NotRemoteAdapter  # type: ignore[attr-defined]
    sys.modules[mod_name] = module
    yield module
    sys.modules.pop(mod_name, None)


def test_load_remote_adapter_uses_from_config(fake_remote_module: types.ModuleType) -> None:
    adapter = load_remote_adapter(
        "coral_test_fake_remote_adapter:FakeRemoteAdapter",
        {"prefix": "remote-agent"},
    )

    states = adapter.collect_metrics()
    assert states[0].agent_id == "remote-agent-1"


def test_load_remote_adapter_rejects_non_protocol(fake_remote_module: types.ModuleType) -> None:
    with pytest.raises(TypeError, match="RemoteRuntimeAdapter protocol"):
        load_remote_adapter("coral_test_fake_remote_adapter:NotRemoteAdapter")


def test_remote_state_bridge_writes_index_and_agent_file(tmp_path: Path) -> None:
    state_dir = tmp_path / ".coral" / "public" / "remote_state"
    bridge = RemoteStateBridge(_FakeRemoteAdapter(prefix="strategy"), state_dir)

    states = bridge.sync_once()

    assert len(states) == 1
    index = read_remote_state(tmp_path / ".coral")
    assert index is not None
    assert index["runtime_type"] == "fake"
    assert index["agents"][0]["agent_id"] == "strategy-1"
    assert index["agents"][0]["metrics"] == {"score": 0.42}

    agent_payload = json.loads((state_dir / "strategy-1.json").read_text())
    assert agent_payload["artifacts"] == {"trace": "trace-1"}


def test_remote_state_bridge_encodes_agent_id_for_filename(tmp_path: Path) -> None:
    state_dir = tmp_path / ".coral" / "public" / "remote_state"
    bridge = RemoteStateBridge(_UnsafeIdRemoteAdapter(), state_dir)

    bridge.sync_once()

    assert (state_dir / "..%2Fremote%2Fagent.json").exists()
    assert not (tmp_path / ".coral" / "public" / "remote").exists()
    index = read_remote_state(tmp_path / ".coral")
    assert index is not None
    assert index["agents"][0]["agent_id"] == "../remote/agent"
