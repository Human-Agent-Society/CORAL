"""Tests for the resume-time context compaction feature."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from coral.agent.builtin.claude_code import ClaudeCodeRuntime
from coral.agent.builtin.codex import CodexRuntime
from coral.agent.builtin.kiro import KiroRuntime
from coral.agent.builtin.opencode import OpenCodeRuntime
from coral.config import CoralConfig


def _make_worktree(tmp_path: Path, agent_id: str = "agent-1") -> Path:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".coral_agent_id").write_text(agent_id)
    (worktree / ".venv" / "bin").mkdir(parents=True)
    return worktree


def test_compact_session_only_on_claude_code():
    """Only Claude Code exposes compact_session; other runtimes have no stub."""
    assert callable(getattr(ClaudeCodeRuntime(), "compact_session", None))
    for runtime in (CodexRuntime(), OpenCodeRuntime(), KiroRuntime()):
        assert getattr(runtime, "compact_session", None) is None


def test_claude_compact_session_invokes_claude(tmp_path: Path) -> None:
    worktree = _make_worktree(tmp_path)
    log_dir = tmp_path / "logs"

    completed = subprocess.CompletedProcess(args=[], returncode=0)
    with patch("coral.agent.builtin.claude_code.subprocess.run", return_value=completed) as run:
        ok = ClaudeCodeRuntime().compact_session(
            session_id="abc-123",
            worktree_path=worktree,
            model="opus",
            log_dir=log_dir,
        )

    assert ok is True
    run.assert_called_once()
    cmd = run.call_args.args[0]
    assert cmd[0] == "claude"
    assert "/compact" in cmd
    assert "--resume" in cmd
    assert "abc-123" in cmd
    assert "--model" in cmd and "opus" in cmd
    # Log file should be in the supplied log_dir
    assert log_dir.exists()
    assert any(log_dir.iterdir())


def test_claude_compact_session_handles_timeout(tmp_path: Path) -> None:
    worktree = _make_worktree(tmp_path)
    log_dir = tmp_path / "logs"

    with patch(
        "coral.agent.builtin.claude_code.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["claude"], timeout=1),
    ):
        ok = ClaudeCodeRuntime().compact_session(
            session_id="abc-123",
            worktree_path=worktree,
            log_dir=log_dir,
            timeout=1.0,
        )

    assert ok is False


def test_claude_compact_session_handles_nonzero_exit(tmp_path: Path) -> None:
    worktree = _make_worktree(tmp_path)
    log_dir = tmp_path / "logs"

    completed = subprocess.CompletedProcess(args=[], returncode=2)
    with patch("coral.agent.builtin.claude_code.subprocess.run", return_value=completed):
        ok = ClaudeCodeRuntime().compact_session(
            session_id="abc-123",
            worktree_path=worktree,
            log_dir=log_dir,
        )

    assert ok is False


def test_claude_compact_session_routes_through_gateway(tmp_path: Path) -> None:
    worktree = _make_worktree(tmp_path)

    completed = subprocess.CompletedProcess(args=[], returncode=0)
    with patch("coral.agent.builtin.claude_code.subprocess.run", return_value=completed) as run:
        ClaudeCodeRuntime().compact_session(
            session_id="abc-123",
            worktree_path=worktree,
            log_dir=tmp_path / "logs",
            gateway_url="http://gateway:1234",
            gateway_api_key="proxy-key",
        )

    env = run.call_args.kwargs["env"]
    assert env["ANTHROPIC_BASE_URL"] == "http://gateway:1234"
    assert env["ANTHROPIC_API_KEY"] == "proxy-key"


def test_compact_helper_is_noop_for_non_claude_runtime(tmp_path: Path) -> None:
    """`_compact_session_for` short-circuits when runtime lacks compact_session."""
    from coral.agent.manager import AgentManager
    from coral.workspace import ProjectPaths

    coral_dir = tmp_path / ".coral"
    (coral_dir / "public").mkdir(parents=True)
    paths = ProjectPaths(
        results_dir=tmp_path / "results",
        task_dir=tmp_path,
        run_dir=tmp_path / "run",
        coral_dir=coral_dir,
        agents_dir=tmp_path / "agents",
        repo_dir=tmp_path / "repo",
    )
    cfg = CoralConfig.from_dict({
        "task": {"name": "t", "description": "d"},
        "agents": {"runtime": "codex"},
    })
    manager = AgentManager(cfg, verbose=False)
    manager.paths = paths
    # Codex runtime has no compact_session — should silently skip without raising.
    manager._compact_session_for("agent-1", tmp_path, "sid-xyz")


def _make_setup_patches(tmp_path: Path):
    """Patch every module-level helper inside _setup_and_start_agent so we
    can drive just the compaction branch."""
    return [
        patch("coral.agent.manager.create_agent_worktree", return_value=tmp_path / "wt"),
        patch("coral.agent.manager.setup_gitignore"),
        patch("coral.agent.manager.setup_worktree_env"),
        patch("coral.agent.manager.write_coral_dir"),
        patch("coral.agent.manager.setup_shared_state"),
        patch("coral.agent.manager.setup_claude_settings"),
        patch("coral.agent.manager.read_agent_heartbeat", return_value={"actions": []}),
        patch("coral.agent.manager.write_agent_id"),
        patch("coral.agent.manager.generate_coral_md", return_value="# fake"),
    ]


def _build_manager(tmp_path: Path):
    from coral.agent.manager import AgentManager
    from coral.workspace import ProjectPaths

    coral_dir = tmp_path / ".coral"
    (coral_dir / "public" / "logs").mkdir(parents=True)
    paths = ProjectPaths(
        results_dir=tmp_path / "results",
        task_dir=tmp_path,
        run_dir=tmp_path,
        coral_dir=coral_dir,
        agents_dir=tmp_path / "agents",
        repo_dir=tmp_path / "repo",
    )

    cfg = CoralConfig.from_dict({
        "task": {"name": "t", "description": "d"},
        "agents": {"count": 1, "model": "opus", "runtime": "claude-code"},
    })
    manager = AgentManager(cfg, verbose=False)
    manager.paths = paths
    return manager, tmp_path / "wt"


def test_setup_and_start_agent_compacts_on_resume(tmp_path: Path) -> None:
    """Every resume goes through _setup_and_start_agent and triggers
    compaction (the call is a no-op on runtimes without compact_session)."""
    manager, wt = _build_manager(tmp_path)
    wt.mkdir(exist_ok=True)

    with patch.object(manager, "_compact_session_for") as compact_for, \
         patch.object(manager.runtime, "start", return_value=MagicMock()):
        for p in _make_setup_patches(tmp_path):
            p.start()
        try:
            manager._setup_and_start_agent("agent-1", resume_session_id="sid-xyz")
        finally:
            patch.stopall()

    compact_for.assert_called_once_with("agent-1", wt, "sid-xyz")


def test_setup_and_start_agent_skips_compact_on_fresh_start(tmp_path: Path) -> None:
    """No resume_session_id → no compaction (fresh start path)."""
    manager, wt = _build_manager(tmp_path)
    wt.mkdir(exist_ok=True)

    with patch.object(manager, "_compact_session_for") as compact_for, \
         patch.object(manager.runtime, "start", return_value=MagicMock()):
        for p in _make_setup_patches(tmp_path):
            p.start()
        try:
            manager._setup_and_start_agent("agent-1", resume_session_id=None)
        finally:
            patch.stopall()

    compact_for.assert_not_called()
