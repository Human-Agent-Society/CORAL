"""Remote proxy worker recovery behavior."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import coral.agent.remote_proxy_worker as worker
from coral.agent.remote import RemoteAgentHandle, RemoteAgentSpec, RemoteAgentState


class _RecoverableAdapter:
    runtime_type = "recoverable"
    deployed: list[RemoteAgentHandle] = []
    deploy_calls = 0
    invoke_calls = 0

    def __init__(self) -> None:
        pass

    def deploy(self, agent_spec: RemoteAgentSpec) -> RemoteAgentHandle:
        type(self).deploy_calls += 1
        handle = RemoteAgentHandle(
            agent_id=agent_spec.agent_id,
            runtime_type=self.runtime_type,
            runtime_id=f"runtime-{agent_spec.agent_id}",
        )
        type(self).deployed.append(handle)
        return handle

    def invoke(self, handle: RemoteAgentHandle, payload: dict[str, Any]) -> dict[str, Any]:
        type(self).invoke_calls += 1
        return {"operation_id": payload["operation_id"], "runtime_id": handle.runtime_id}

    def list_agents(self) -> list[RemoteAgentHandle]:
        return list(type(self).deployed)

    def collect_metrics(self) -> list[RemoteAgentState]:
        return []


def test_worker_reuses_persisted_handle_and_completed_operation(tmp_path: Path) -> None:
    module_name = "coral_test_recoverable_remote_adapter"
    module = types.ModuleType(module_name)
    module.RecoverableAdapter = _RecoverableAdapter  # type: ignore[attr-defined]
    sys.modules[module_name] = module
    _RecoverableAdapter.deployed = []
    _RecoverableAdapter.deploy_calls = 0
    _RecoverableAdapter.invoke_calls = 0
    worker._STOP = True

    try:
        kwargs = {
            "adapter_path": f"{module_name}:RecoverableAdapter",
            "adapter_config": {},
            "agent_id": "agent-1",
            "worktree_path": tmp_path / "worktree",
            "state_dir": tmp_path / ".coral" / "public" / "remote_state",
            "control_dir": tmp_path / "control",
            "log_path": tmp_path / "remote.log",
            "prompt": "do work",
            "task_name": "Task",
            "task_description": "Description",
            "operation_id": "agent-1:op",
            "grant": None,
            "sync_interval_seconds": 1.0,
        }
        kwargs["worktree_path"].mkdir()

        worker.run_proxy(**kwargs)
        worker.run_proxy(**kwargs)

        assert _RecoverableAdapter.deploy_calls == 1
        assert _RecoverableAdapter.invoke_calls == 1
        assert (tmp_path / "control" / "handles" / "agent-1.json").exists()
        assert (tmp_path / "control" / "operations" / "agent-1:op.json").exists()
    finally:
        sys.modules.pop(module_name, None)
        worker._STOP = False
