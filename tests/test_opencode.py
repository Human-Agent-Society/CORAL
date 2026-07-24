"""OpenCode runtime command construction."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from coral.agent.builtin.opencode import OpenCodeRuntime


class _FakePopen:
    captured: list[dict[str, Any]] = []

    def __init__(self, cmd: list[str], **kwargs: Any) -> None:
        self.pid = 12345
        self.returncode = None
        self.stdout = None
        self.captured.append({"cmd": cmd, **kwargs})


def test_start_pins_opencode_project_to_worktree(tmp_path: Path, monkeypatch) -> None:
    """A parent git repo must not make OpenCode operate outside the worktree."""
    worktree = tmp_path / "parent-repo" / "results" / "agents" / "agent-1"
    worktree.mkdir(parents=True)
    (worktree / ".coral_agent_id").write_text("agent-1")
    coral_md = worktree / "CORAL.md"
    coral_md.write_text("instructions")
    log_dir = tmp_path / "logs"

    _FakePopen.captured = []
    monkeypatch.setattr(subprocess, "Popen", _FakePopen)

    OpenCodeRuntime().start(
        worktree_path=worktree,
        coral_md_path=coral_md,
        model="mafia/glm-5.2",
        log_dir=log_dir,
        prompt="work on the task",
    )

    assert len(_FakePopen.captured) == 1
    invocation = _FakePopen.captured[0]
    assert invocation["cmd"] == [
        "opencode",
        "run",
        "--model",
        "mafia/glm-5.2",
        "--format",
        "json",
        "--dir",
        str(worktree),
        "work on the task",
    ]
    assert invocation["cwd"] == str(worktree)


def test_classify_exit_rejects_malformed_resumable_session(tmp_path: Path) -> None:
    log = tmp_path / "agent.log"
    log.write_text(
        '{"type":"error","error":{"data":{"message":'
        '"The request is invalid: Assistant message content at index 33 '
        'cannot be empty."}}}\n'
    )

    classification = OpenCodeRuntime().classify_exit(
        log,
        exit_code=1,
        uptime_seconds=120.0,
    )

    assert classification == "session_error"
