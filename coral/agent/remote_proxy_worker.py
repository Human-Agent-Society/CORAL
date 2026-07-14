"""Long-running local proxy process for remote agent runtimes."""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path
from typing import Any

from coral.agent.remote import (
    RemoteAgentHandle,
    RemoteAgentSpec,
    RemoteAgentState,
    RemoteStateBridge,
    RemoteWorkspaceGrant,
    load_remote_adapter,
    utc_now_iso,
)

_STOP = False


def _handle_stop(signum: int, frame: object) -> None:
    global _STOP
    _STOP = True


def _write_event(log_path: Path, event: dict[str, Any]) -> None:
    payload = {"type": "remote_proxy", "timestamp": utc_now_iso(), **event}
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(payload, sort_keys=True) + "\n")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp_path, path)


def _load_handle(path: Path) -> RemoteAgentHandle | None:
    payload = _read_json(path)
    if not payload:
        return None
    try:
        return RemoteAgentHandle(
            agent_id=str(payload["agent_id"]),
            runtime_type=str(payload["runtime_type"]),
            runtime_id=str(payload["runtime_id"]),
            endpoint=payload.get("endpoint"),
            status=payload.get("status"),
            metadata=dict(payload.get("metadata") or {}),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _handle_reachable(adapter: Any, handle: RemoteAgentHandle) -> bool:
    try:
        handles = adapter.list_agents()
    except Exception:
        return True
    for candidate in handles:
        if candidate.runtime_id == handle.runtime_id:
            return True
    return False


def _remote_grant_from_json(raw: str) -> RemoteWorkspaceGrant | None:
    if not raw:
        return None
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        return None
    return RemoteWorkspaceGrant(
        grant_id=str(payload["grant_id"]),
        issuer=str(payload["issuer"]),
        workspace_id=str(payload["workspace_id"]),
        permitted_operations=list(payload.get("permitted_operations") or []),
        memory_namespace=payload.get("memory_namespace"),
        artifact_namespace=payload.get("artifact_namespace"),
        expires_at=payload.get("expires_at"),
        metadata=dict(payload.get("metadata") or {}),
    )


def run_proxy(
    adapter_path: str,
    adapter_config: dict[str, Any],
    agent_id: str,
    worktree_path: Path,
    state_dir: Path,
    control_dir: Path,
    log_path: Path,
    prompt: str,
    task_name: str | None,
    task_description: str | None,
    operation_id: str,
    grant: RemoteWorkspaceGrant | None,
    sync_interval_seconds: float,
) -> None:
    """Deploy/invoke a remote agent and keep syncing its state."""
    adapter = load_remote_adapter(adapter_path, adapter_config)
    bridge = RemoteStateBridge(adapter, state_dir)
    handle_path = control_dir / "handles" / f"{agent_id}.json"
    operation_path = control_dir / "operations" / f"{operation_id}.json"
    spec = RemoteAgentSpec(
        agent_id=agent_id,
        name=task_name or agent_id,
        code_path=worktree_path,
        grant=grant,
        metadata={"task_description": task_description or ""},
    )

    handle_degraded = False
    handle = _load_handle(handle_path)
    if handle is not None:
        _write_event(log_path, {"event": "reconnected", "handle": handle.to_dict()})
        if not _handle_reachable(adapter, handle):
            handle_degraded = True
            bridge.write_states(
                [
                    RemoteAgentState(
                        agent_id=agent_id,
                        runtime_type=handle.runtime_type,
                        runtime_id=handle.runtime_id,
                        status="degraded",
                        recovery={
                            "reason": "remote_handle_missing",
                            "operation_id": operation_id,
                        },
                    )
                ]
            )
            _write_event(
                log_path,
                {
                    "event": "degraded",
                    "reason": "remote_handle_missing",
                    "operation_id": operation_id,
                },
            )
    else:
        handle = adapter.deploy(spec)
        _write_json(handle_path, handle.to_dict())
        _write_event(log_path, {"event": "deployed", "handle": handle.to_dict()})

    operation = _read_json(operation_path) or {}
    if handle_degraded:
        _write_event(
            log_path,
            {"event": "invoke_deferred", "reason": "remote_handle_missing"},
        )
    elif operation.get("status") == "completed":
        _write_event(log_path, {"event": "invoke_skipped", "operation_id": operation_id})
    else:
        _write_json(
            operation_path,
            {
                "operation_id": operation_id,
                "agent_id": agent_id,
                "runtime_id": handle.runtime_id,
                "status": "started",
                "started_at": operation.get("started_at") or utc_now_iso(),
            },
        )
        response = adapter.invoke(
            handle,
            {
                "operation_id": operation_id,
                "prompt": prompt,
                "task_name": task_name,
                "task_description": task_description,
                "worktree_path": str(worktree_path),
                "grant": grant.to_dict() if grant else None,
            },
        )
        _write_json(
            operation_path,
            {
                "operation_id": operation_id,
                "agent_id": agent_id,
                "runtime_id": handle.runtime_id,
                "status": "completed",
                "started_at": operation.get("started_at") or utc_now_iso(),
                "completed_at": utc_now_iso(),
                "response": response,
            },
        )
        _write_event(
            log_path,
            {"event": "invoked", "operation_id": operation_id, "response": response},
        )

    while not _STOP:
        states = bridge.sync_once()
        _write_event(log_path, {"event": "synced", "agents": len(states)})
        time.sleep(sync_interval_seconds)

    _write_event(log_path, {"event": "stopped"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--config-json", default="{}")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--worktree-path", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--control-dir", type=Path, required=True)
    parser.add_argument("--log-path", type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--task-name", default="")
    parser.add_argument("--task-description", default="")
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--grant-json", default="")
    parser.add_argument("--sync-interval-seconds", type=float, default=30.0)
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    raw_config = os.environ.get("CORAL_REMOTE_PROXY_CONFIG_JSON", args.config_json)
    adapter_config = json.loads(raw_config)
    run_proxy(
        adapter_path=args.adapter,
        adapter_config=adapter_config,
        agent_id=args.agent_id,
        worktree_path=args.worktree_path,
        state_dir=args.state_dir,
        control_dir=args.control_dir,
        log_path=args.log_path,
        prompt=args.prompt,
        task_name=args.task_name or None,
        task_description=args.task_description or None,
        operation_id=args.operation_id,
        grant=_remote_grant_from_json(args.grant_json),
        sync_interval_seconds=args.sync_interval_seconds,
    )


if __name__ == "__main__":
    main()
