"""Tests for the resume-time context compaction feature."""

from __future__ import annotations

import argparse
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


def _make_manager_with_paths(tmp_path: Path, *, auto_compact: bool):
    """Helper: build a real AgentManager with a fake ProjectPaths.

    Stubs out heavy lifecycle hooks so we can drive the compact code paths
    in isolation.
    """
    from coral.agent.manager import AgentManager
    from coral.workspace import ProjectPaths

    coral_dir = tmp_path / ".coral"
    (coral_dir / "public").mkdir(parents=True)
    (coral_dir / "private").mkdir(parents=True)
    agents_dir = tmp_path / "agents"
    (agents_dir / "agent-1").mkdir(parents=True)
    (agents_dir / "agent-1" / ".coral_agent_id").write_text("agent-1")
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    paths = ProjectPaths(
        results_dir=tmp_path / "results",
        task_dir=tmp_path,
        run_dir=run_dir,
        coral_dir=coral_dir,
        agents_dir=agents_dir,
        repo_dir=repo_dir,
    )
    (coral_dir / "public" / "sessions.json").write_text('{"agent-1": "sid-xyz"}')

    cfg = CoralConfig.from_dict({
        "task": {"name": "t", "description": "d"},
        "agents": {"count": 1, "model": "opus", "runtime": "claude-code"},
    })
    manager = AgentManager(cfg, verbose=False, auto_compact=auto_compact)
    manager._start_gateway_if_enabled = MagicMock()  # type: ignore[method-assign]
    manager._start_grader_daemon = MagicMock()  # type: ignore[method-assign]
    manager._kill_old_agent_processes = MagicMock()  # type: ignore[method-assign]
    manager._setup_and_start_agent = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(agent_id="agent-1", session_id="sid-xyz")
    )
    manager._write_pid_file = MagicMock()  # type: ignore[method-assign]
    return manager, paths


def test_resume_all_passes_session_through_to_setup(tmp_path: Path) -> None:
    """resume_all delegates to _setup_and_start_agent (where compaction now
    happens, gated on the auto_compact flag)."""
    manager, paths = _make_manager_with_paths(tmp_path, auto_compact=True)
    with patch("coral.agent.manager._validate_sessions", return_value={"agent-1": "sid-xyz"}):
        manager.resume_all(paths)
    manager._setup_and_start_agent.assert_called_once()
    kwargs = manager._setup_and_start_agent.call_args.kwargs
    assert kwargs["resume_session_id"] == "sid-xyz"


def test_setup_and_start_agent_compacts_when_auto_compact(tmp_path: Path) -> None:
    """With auto_compact=True, every resume call (including post-eval restart)
    should run compact_session before runtime.start."""
    from coral.agent.manager import AgentManager

    cfg = CoralConfig.from_dict({
        "task": {"name": "t", "description": "d"},
        "agents": {"count": 1, "model": "opus", "runtime": "claude-code"},
    })
    manager = AgentManager(cfg, verbose=False, auto_compact=True)

    # _setup_and_start_agent needs paths set
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
    manager.paths = paths

    with patch.object(manager, "_compact_session_for") as compact_for, \
         patch("coral.agent.manager.create_agent_worktree", return_value=tmp_path / "wt"), \
         patch("coral.agent.manager.setup_gitignore"), \
         patch("coral.agent.manager.setup_worktree_env"), \
         patch("coral.agent.manager.write_coral_dir"), \
         patch("coral.agent.manager.setup_shared_state"), \
         patch("coral.agent.manager.setup_claude_settings"), \
         patch("coral.agent.manager.read_agent_heartbeat", return_value={"actions": []}), \
         patch("coral.agent.manager.write_agent_id"), \
         patch("coral.agent.manager.generate_coral_md", return_value="# fake"), \
         patch.object(manager.runtime, "start", return_value=MagicMock()):
        # Make sure the worktree path the patched create_agent_worktree returns exists
        (tmp_path / "wt").mkdir(exist_ok=True)
        manager._setup_and_start_agent("agent-1", resume_session_id="sid-xyz")

    compact_for.assert_called_once_with("agent-1", tmp_path / "wt", "sid-xyz")


def test_setup_and_start_agent_skips_compact_on_fresh_start(tmp_path: Path) -> None:
    """No resume_session_id → no compaction even if auto_compact is True."""
    from coral.agent.manager import AgentManager
    from coral.workspace import ProjectPaths

    cfg = CoralConfig.from_dict({
        "task": {"name": "t", "description": "d"},
        "agents": {"count": 1, "model": "opus", "runtime": "claude-code"},
    })
    manager = AgentManager(cfg, verbose=False, auto_compact=True)

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
    manager.paths = paths

    with patch.object(manager, "_compact_session_for") as compact_for, \
         patch("coral.agent.manager.create_agent_worktree", return_value=tmp_path / "wt"), \
         patch("coral.agent.manager.setup_gitignore"), \
         patch("coral.agent.manager.setup_worktree_env"), \
         patch("coral.agent.manager.write_coral_dir"), \
         patch("coral.agent.manager.setup_shared_state"), \
         patch("coral.agent.manager.setup_claude_settings"), \
         patch("coral.agent.manager.read_agent_heartbeat", return_value={"actions": []}), \
         patch("coral.agent.manager.write_agent_id"), \
         patch("coral.agent.manager.generate_coral_md", return_value="# fake"), \
         patch.object(manager.runtime, "start", return_value=MagicMock()):
        (tmp_path / "wt").mkdir(exist_ok=True)
        manager._setup_and_start_agent("agent-1", resume_session_id=None)

    compact_for.assert_not_called()


def test_setup_and_start_agent_skips_compact_when_flag_off(tmp_path: Path) -> None:
    """auto_compact=False → never compact, even on resume."""
    from coral.agent.manager import AgentManager
    from coral.workspace import ProjectPaths

    cfg = CoralConfig.from_dict({
        "task": {"name": "t", "description": "d"},
        "agents": {"count": 1, "model": "opus", "runtime": "claude-code"},
    })
    manager = AgentManager(cfg, verbose=False, auto_compact=False)

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
    manager.paths = paths

    with patch.object(manager, "_compact_session_for") as compact_for, \
         patch("coral.agent.manager.create_agent_worktree", return_value=tmp_path / "wt"), \
         patch("coral.agent.manager.setup_gitignore"), \
         patch("coral.agent.manager.setup_worktree_env"), \
         patch("coral.agent.manager.write_coral_dir"), \
         patch("coral.agent.manager.setup_shared_state"), \
         patch("coral.agent.manager.setup_claude_settings"), \
         patch("coral.agent.manager.read_agent_heartbeat", return_value={"actions": []}), \
         patch("coral.agent.manager.write_agent_id"), \
         patch("coral.agent.manager.generate_coral_md", return_value="# fake"), \
         patch.object(manager.runtime, "start", return_value=MagicMock()):
        (tmp_path / "wt").mkdir(exist_ok=True)
        manager._setup_and_start_agent("agent-1", resume_session_id="sid-xyz")

    compact_for.assert_not_called()


def test_cli_resume_parses_compact_flag() -> None:
    """The --compact flag must reach args.compact when resume is invoked."""
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command")
    pr = sub.add_parser("resume")
    pr.add_argument("--compact", action="store_true", default=False)
    pr.add_argument("overrides", nargs="*", default=[])

    assert p.parse_args(["resume", "--compact"]).compact is True
    assert p.parse_args(["resume"]).compact is False
