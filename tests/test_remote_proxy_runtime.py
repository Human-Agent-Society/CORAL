"""Remote proxy runtime behavior."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from coral.agent.builtin.remote_proxy import RemoteProxyRuntime
from coral.agent.registry import default_model_for_runtime, get_runtime


class _FakeProcess:
    pid = 12345
    stdout = None
    stderr = None

    def poll(self) -> int | None:
        return None


def test_registry_resolves_remote_proxy_runtime() -> None:
    assert isinstance(get_runtime("remote_proxy"), RemoteProxyRuntime)
    assert isinstance(get_runtime("remote"), RemoteProxyRuntime)
    assert default_model_for_runtime("remote_proxy") == "remote"


def test_remote_proxy_start_builds_worker_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".coral_agent_id").write_text("agent-1")
    coral_dir = tmp_path / ".coral"
    (worktree / ".coral_dir").write_text(str(coral_dir))
    log_dir = coral_dir / "public" / "logs"

    captured: dict[str, Any] = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    handle = RemoteProxyRuntime().start(
        worktree_path=worktree,
        coral_md_path=worktree / "AGENTS.md",
        runtime_options={
            "adapter": "pkg.remote:Adapter",
            "config": {"region": "us-west-2"},
            "sync_interval_seconds": 5,
        },
        log_dir=log_dir,
        prompt="start remote work",
        task_name="Task",
        task_description="Description",
    )

    cmd = captured["cmd"]
    assert cmd[:3] == [cmd[0], "-m", "coral.agent.remote_proxy_worker"]
    assert "--adapter" in cmd
    assert cmd[cmd.index("--adapter") + 1] == "pkg.remote:Adapter"
    config_json = cmd[cmd.index("--config-json") + 1]
    assert json.loads(config_json) == {"region": "us-west-2"}
    assert cmd[cmd.index("--state-dir") + 1] == str(coral_dir / "public" / "remote_state")
    assert cmd[cmd.index("--sync-interval-seconds") + 1] == "5.0"
    assert captured["kwargs"]["cwd"] == str(worktree)
    assert handle.agent_id == "agent-1"
    assert handle.alive is True


def test_remote_proxy_requires_adapter(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".coral_agent_id").write_text("agent-1")

    try:
        RemoteProxyRuntime().start(
            worktree_path=worktree,
            coral_md_path=worktree / "AGENTS.md",
            runtime_options={},
        )
    except ValueError as exc:
        assert "runtime_options.adapter" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError")
