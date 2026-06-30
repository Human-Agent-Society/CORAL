"""Long-running local proxy process for remote agent runtimes."""

from __future__ import annotations

import argparse
import json
import signal
import time
from pathlib import Path
from typing import Any

from coral.agent.remote import RemoteAgentSpec, RemoteStateBridge, load_remote_adapter, utc_now_iso

_STOP = False


def _handle_stop(signum: int, frame: object) -> None:
    global _STOP
    _STOP = True


def _write_event(log_path: Path, event: dict[str, Any]) -> None:
    payload = {"type": "remote_proxy", "timestamp": utc_now_iso(), **event}
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(payload, sort_keys=True) + "\n")


def run_proxy(
    adapter_path: str,
    adapter_config: dict[str, Any],
    agent_id: str,
    worktree_path: Path,
    state_dir: Path,
    log_path: Path,
    prompt: str,
    task_name: str | None,
    task_description: str | None,
    sync_interval_seconds: float,
) -> None:
    """Deploy/invoke a remote agent and keep syncing its state."""
    adapter = load_remote_adapter(adapter_path, adapter_config)
    bridge = RemoteStateBridge(adapter, state_dir)
    spec = RemoteAgentSpec(
        agent_id=agent_id,
        name=task_name or agent_id,
        code_path=worktree_path,
        metadata={"task_description": task_description or ""},
    )
    handle = adapter.deploy(spec)
    _write_event(log_path, {"event": "deployed", "handle": handle.to_dict()})

    response = adapter.invoke(
        handle,
        {
            "prompt": prompt,
            "task_name": task_name,
            "task_description": task_description,
            "worktree_path": str(worktree_path),
        },
    )
    _write_event(log_path, {"event": "invoked", "response": response})

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
    parser.add_argument("--log-path", type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--task-name", default="")
    parser.add_argument("--task-description", default="")
    parser.add_argument("--sync-interval-seconds", type=float, default=30.0)
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    adapter_config = json.loads(args.config_json)
    run_proxy(
        adapter_path=args.adapter,
        adapter_config=adapter_config,
        agent_id=args.agent_id,
        worktree_path=args.worktree_path,
        state_dir=args.state_dir,
        log_path=args.log_path,
        prompt=args.prompt,
        task_name=args.task_name or None,
        task_description=args.task_description or None,
        sync_interval_seconds=args.sync_interval_seconds,
    )


if __name__ == "__main__":
    main()
