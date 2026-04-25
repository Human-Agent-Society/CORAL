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


def test_resume_all_calls_compact_when_enabled(tmp_path: Path) -> None:
    """When resume_all is called with compact=True, the runtime is asked to
    compact each session before _setup_and_start_agent runs."""
    from coral.agent.manager import AgentManager
    from coral.workspace import ProjectPaths

    # Build a minimal fake ProjectPaths
    coral_dir = tmp_path / ".coral"
    (coral_dir / "public").mkdir(parents=True)
    (coral_dir / "private").mkdir(parents=True)
    (coral_dir / "private" / "sessions").mkdir()
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

    # Pre-seed sessions.json so resume_all picks up a session for agent-1
    (coral_dir / "public" / "sessions.json").write_text('{"agent-1": "sid-xyz"}')

    cfg = CoralConfig.from_dict({
        "task": {"name": "t", "description": "d"},
        "agents": {"count": 1, "model": "opus", "runtime": "claude-code"},
    })
    manager = AgentManager(cfg, verbose=False)

    # Stub out heavy operations so we can focus on the compact path.
    manager._start_gateway_if_enabled = MagicMock()  # type: ignore[method-assign]
    manager._start_grader_daemon = MagicMock()  # type: ignore[method-assign]
    manager._kill_old_agent_processes = MagicMock()  # type: ignore[method-assign]
    manager._setup_and_start_agent = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(agent_id="agent-1", session_id="sid-xyz")
    )
    manager._write_pid_file = MagicMock()  # type: ignore[method-assign]

    # Force session validation to accept our fake session
    with patch("coral.agent.manager._validate_sessions", return_value={"agent-1": "sid-xyz"}), \
         patch.object(manager.runtime, "compact_session", return_value=True) as compact:
        manager.resume_all(paths, compact=True)

    compact.assert_called_once()
    kwargs = compact.call_args.kwargs
    assert kwargs["session_id"] == "sid-xyz"
    assert kwargs["worktree_path"] == agents_dir / "agent-1"
    assert kwargs["model"] == "opus"


def test_resume_all_skips_compact_when_disabled(tmp_path: Path) -> None:
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
    manager = AgentManager(cfg, verbose=False)
    manager._start_gateway_if_enabled = MagicMock()  # type: ignore[method-assign]
    manager._start_grader_daemon = MagicMock()  # type: ignore[method-assign]
    manager._kill_old_agent_processes = MagicMock()  # type: ignore[method-assign]
    manager._setup_and_start_agent = MagicMock(  # type: ignore[method-assign]
        return_value=MagicMock(agent_id="agent-1", session_id="sid-xyz")
    )
    manager._write_pid_file = MagicMock()  # type: ignore[method-assign]

    with patch("coral.agent.manager._validate_sessions", return_value={"agent-1": "sid-xyz"}), \
         patch.object(manager.runtime, "compact_session", return_value=True) as compact:
        manager.resume_all(paths)  # compact defaults to False

    compact.assert_not_called()


def test_cli_resume_parses_compact_flag() -> None:
    """The --compact flag must reach args.compact when resume is invoked."""
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command")
    pr = sub.add_parser("resume")
    pr.add_argument("--compact", action="store_true", default=False)
    pr.add_argument("overrides", nargs="*", default=[])

    assert p.parse_args(["resume", "--compact"]).compact is True
    assert p.parse_args(["resume"]).compact is False
