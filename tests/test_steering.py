"""Steer-on-resume queue and dashboard endpoint behavior."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

from coral.agent.manager import AgentManager
from coral.config import CoralConfig
from coral.hub.attempts import read_attempt, write_attempt
from coral.hub.steering import (
    ContinueFromAction,
    MarkBestAction,
    enqueue,
    mark_applied,
    read_pending,
)
from coral.types import Attempt
from coral.web.api import get_steering, post_steer
from coral.workspace import ProjectPaths


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit_file(repo: Path, name: str, content: str, message: str) -> str:
    (repo / name).write_text(content)
    _git(repo, "add", name)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _stub_manager_for_resume(
    manager: AgentManager, monkeypatch, agent_dirs: dict[str, Path]
) -> list:
    handles = []

    monkeypatch.setattr(manager, "_start_gateway_if_enabled", lambda: None)
    monkeypatch.setattr(manager, "_start_grader_daemon", lambda: None)
    monkeypatch.setattr(manager, "_kill_old_agent_processes", lambda: None)
    monkeypatch.setattr(manager, "_load_saved_sessions", lambda: {})
    monkeypatch.setattr("coral.agent.manager._validate_sessions", lambda sessions, coral_dir: {})
    monkeypatch.setattr(manager, "_write_pid_file", lambda: None)
    monkeypatch.setattr("atexit.register", lambda fn: None)

    def fake_setup(agent_id: str, **kwargs):
        handle = SimpleNamespace(
            agent_id=agent_id,
            process=SimpleNamespace(pid=123, poll=lambda: None),
            worktree_path=agent_dirs[agent_id],
            log_path=agent_dirs[agent_id] / "agent.log",
            session_id=None,
            prompt=kwargs.get("prompt"),
        )
        handles.append(handle)
        return handle

    monkeypatch.setattr(manager, "_setup_and_start_agent", fake_setup)
    return handles


def _attempt(commit: str, score: float = 0.5) -> Attempt:
    return Attempt(
        commit_hash=commit,
        agent_id="agent-1",
        title=f"attempt {commit}",
        score=score,
        status="improved",
        parent_hash=None,
        timestamp="2026-06-01T10:00:00Z",
    )


def _request(coral_dir: Path, body: dict | None = None):
    async def json_body():
        return body or {}

    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(coral_dir=coral_dir)),
        path_params={},
        json=json_body,
    )


def test_steering_queue_round_trip(tmp_path: Path) -> None:
    coral_dir = tmp_path / ".coral"

    action = enqueue(
        coral_dir,
        ContinueFromAction(hash="abc123", instruction="try the cached parser"),
    )
    enqueue(coral_dir, MarkBestAction(hash="def456"))

    pending = read_pending(coral_dir)
    assert [a.kind for a in pending] == ["continue_from", "mark_best"]
    assert pending[0].id == action.id
    assert pending[0].hash == "abc123"
    assert pending[0].instruction == "try the cached parser"

    assert mark_applied(coral_dir, action.id) is True
    remaining = read_pending(coral_dir)
    assert [a.kind for a in remaining] == ["mark_best"]
    assert remaining[0].applied_at is None


async def test_post_steer_rejects_writes_while_run_is_alive(tmp_path: Path) -> None:
    coral_dir = tmp_path / ".coral"
    (coral_dir / "public").mkdir(parents=True)
    (coral_dir / "public" / "manager.pid").write_text(str(os.getpid()))

    response = await post_steer(
        _request(coral_dir, {"kind": "continue_from", "hash": "abc123", "instruction": "retry"})
    )

    assert response.status_code == 409
    assert json.loads(response.body)["error"] == "stop the run to steer"
    assert read_pending(coral_dir) == []


async def test_post_steer_queues_when_stopped_and_get_lists_pending(tmp_path: Path) -> None:
    coral_dir = tmp_path / ".coral"
    write_attempt(coral_dir, _attempt("abc123"))

    queued = await post_steer(
        _request(
            coral_dir,
            {"kind": "continue_from", "hash": "abc123", "instruction": "continue from here"},
        )
    )
    assert queued.status_code == 200
    assert json.loads(queued.body)["action"]["kind"] == "continue_from"

    listed = await get_steering(_request(coral_dir))
    payload = json.loads(listed.body)
    assert payload["pending_count"] == 1
    assert payload["actions"][0]["hash"] == "abc123"


async def test_mark_best_updates_attempt_metadata_immediately(tmp_path: Path) -> None:
    coral_dir = tmp_path / ".coral"
    write_attempt(coral_dir, _attempt("abc123", score=0.1))
    write_attempt(coral_dir, _attempt("def456", score=0.9))

    response = await post_steer(_request(coral_dir, {"kind": "mark_best", "hash": "abc123"}))

    assert response.status_code == 200
    assert read_attempt(coral_dir, "abc123").metadata["user_best"] is True  # type: ignore[union-attr]
    assert read_attempt(coral_dir, "def456").metadata.get("user_best") is not True  # type: ignore[union-attr]
    assert read_pending(coral_dir) == []


def test_resume_all_drains_continue_from_actions(tmp_path: Path, monkeypatch) -> None:
    coral_dir = tmp_path / ".coral"
    agents_dir = tmp_path / "agents"
    repo_dir = tmp_path / "repo"
    agent_dir = agents_dir / "agent-1"
    agent_dir.mkdir(parents=True)
    repo_dir.mkdir()
    write_attempt(coral_dir, _attempt("abc123"))
    enqueue(coral_dir, ContinueFromAction(hash="abc123", instruction="build from this branch"))

    paths = ProjectPaths(
        results_dir=tmp_path,
        task_dir=tmp_path,
        run_dir=tmp_path,
        coral_dir=coral_dir,
        agents_dir=agents_dir,
        repo_dir=repo_dir,
    )
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "agents": {"count": 1, "runtime": "claude-code"},
        }
    )
    manager = AgentManager(cfg)
    calls: list[dict] = []

    monkeypatch.setattr(manager, "_start_gateway_if_enabled", lambda: None)
    monkeypatch.setattr(manager, "_start_grader_daemon", lambda: None)
    monkeypatch.setattr(manager, "_kill_old_agent_processes", lambda: None)
    monkeypatch.setattr(manager, "_load_saved_sessions", lambda: {})
    monkeypatch.setattr("coral.agent.manager._validate_sessions", lambda sessions, coral_dir: {})
    monkeypatch.setattr(manager, "_write_pid_file", lambda: None)
    monkeypatch.setattr("atexit.register", lambda fn: None)

    def fake_checkout(worktree_path: Path, target_hash: str) -> None:
        calls.append({"checkout": target_hash, "worktree": worktree_path})

    monkeypatch.setattr(
        "coral.agent.manager._worktree_head_descends_from",
        lambda worktree_path, target_hash: True,
    )
    monkeypatch.setattr("coral.agent.manager._reset_worktree_to_commit", fake_checkout)

    def fake_setup(agent_id: str, **kwargs):
        calls.append({"agent_id": agent_id, **kwargs})
        return SimpleNamespace(
            agent_id=agent_id,
            process=SimpleNamespace(pid=123, poll=lambda: None),
            worktree_path=agent_dir,
            log_path=tmp_path / "agent.log",
            session_id=None,
        )

    monkeypatch.setattr(manager, "_setup_and_start_agent", fake_setup)

    manager.resume_all(paths, instruction="also try SIMD")

    pending = read_pending(coral_dir)
    setup_call = next(c for c in calls if c.get("agent_id") == "agent-1")
    assert pending == []
    assert calls[0] == {"checkout": "abc123", "worktree": agent_dir}
    assert "## Continue from Attempt abc123" in setup_call["prompt"]
    assert "build from this branch" in setup_call["prompt"]
    assert "## Additional Instructions" in setup_call["prompt"]
    assert "also try SIMD" in setup_call["prompt"]


def test_resume_all_applies_cli_resume_from_like_queued_steering(
    tmp_path: Path, monkeypatch
) -> None:
    coral_dir = tmp_path / ".coral"
    agents_dir = tmp_path / "agents"
    repo_dir = tmp_path / "repo"
    agent_dir = agents_dir / "agent-1"
    agent_dir.mkdir(parents=True)
    repo_dir.mkdir()
    write_attempt(coral_dir, _attempt("abc123"))

    paths = ProjectPaths(
        results_dir=tmp_path,
        task_dir=tmp_path,
        run_dir=tmp_path,
        coral_dir=coral_dir,
        agents_dir=agents_dir,
        repo_dir=repo_dir,
    )
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "agents": {"count": 1, "runtime": "claude-code"},
        }
    )
    manager = AgentManager(cfg)
    calls: list[dict] = []

    monkeypatch.setattr(manager, "_start_gateway_if_enabled", lambda: None)
    monkeypatch.setattr(manager, "_start_grader_daemon", lambda: None)
    monkeypatch.setattr(manager, "_kill_old_agent_processes", lambda: None)
    monkeypatch.setattr(manager, "_load_saved_sessions", lambda: {})
    monkeypatch.setattr("coral.agent.manager._validate_sessions", lambda sessions, coral_dir: {})
    monkeypatch.setattr(manager, "_write_pid_file", lambda: None)
    monkeypatch.setattr("atexit.register", lambda fn: None)
    monkeypatch.setattr(
        "coral.agent.manager._reset_worktree_to_commit",
        lambda worktree_path, target_hash: calls.append(
            {"checkout": target_hash, "worktree": worktree_path}
        ),
    )
    monkeypatch.setattr(
        "coral.agent.manager._worktree_head_descends_from",
        lambda worktree_path, target_hash: True,
    )

    def fake_setup(agent_id: str, **kwargs):
        calls.append({"agent_id": agent_id, **kwargs})
        return SimpleNamespace(
            agent_id=agent_id,
            process=SimpleNamespace(pid=123, poll=lambda: None),
            worktree_path=agent_dir,
            log_path=tmp_path / "agent.log",
            session_id=None,
        )

    monkeypatch.setattr(manager, "_setup_and_start_agent", fake_setup)

    manager.resume_all(paths, instruction="try SIMD", resume_from="abc123")

    setup_call = next(c for c in calls if c.get("agent_id") == "agent-1")
    assert calls[0] == {"checkout": "abc123", "worktree": agent_dir}
    assert "## Continue from Attempt abc123" in setup_call["prompt"]
    assert "## Additional Instructions" in setup_call["prompt"]
    assert "try SIMD" in setup_call["prompt"]


def test_resume_from_resets_real_worktree_head(tmp_path: Path, monkeypatch) -> None:
    coral_dir = tmp_path / ".coral"
    agents_dir = tmp_path / "agents"
    repo_dir = tmp_path / "repo"
    agent_dir = agents_dir / "agent-1"
    agent_dir.mkdir(parents=True)

    _git(agent_dir, "init")
    _git(agent_dir, "config", "user.email", "test@example.com")
    _git(agent_dir, "config", "user.name", "Test User")
    target_hash = _commit_file(agent_dir, "solution.txt", "target\n", "target attempt")
    latest_hash = _commit_file(agent_dir, "solution.txt", "latest\n", "latest attempt")
    assert latest_hash != target_hash
    assert _git(agent_dir, "rev-parse", "HEAD") == latest_hash

    repo_dir.mkdir()
    write_attempt(coral_dir, _attempt(target_hash))

    paths = ProjectPaths(
        results_dir=tmp_path,
        task_dir=tmp_path,
        run_dir=tmp_path,
        coral_dir=coral_dir,
        agents_dir=agents_dir,
        repo_dir=repo_dir,
    )
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "agents": {"count": 1, "runtime": "claude-code"},
        }
    )
    manager = AgentManager(cfg)
    prompts: list[str | None] = []

    monkeypatch.setattr(manager, "_start_gateway_if_enabled", lambda: None)
    monkeypatch.setattr(manager, "_start_grader_daemon", lambda: None)
    monkeypatch.setattr(manager, "_kill_old_agent_processes", lambda: None)
    monkeypatch.setattr(manager, "_load_saved_sessions", lambda: {})
    monkeypatch.setattr("coral.agent.manager._validate_sessions", lambda sessions, coral_dir: {})
    monkeypatch.setattr(manager, "_write_pid_file", lambda: None)
    monkeypatch.setattr("atexit.register", lambda fn: None)

    def fake_setup(agent_id: str, **kwargs):
        prompts.append(kwargs.get("prompt"))
        return SimpleNamespace(
            agent_id=agent_id,
            process=SimpleNamespace(pid=123, poll=lambda: None),
            worktree_path=agent_dir,
            log_path=tmp_path / "agent.log",
            session_id=None,
        )

    monkeypatch.setattr(manager, "_setup_and_start_agent", fake_setup)

    manager.resume_all(paths, instruction="continue here", resume_from=target_hash)

    assert _git(agent_dir, "rev-parse", "HEAD") == target_hash
    assert (agent_dir / "solution.txt").read_text() == "target\n"
    assert prompts and f"## Continue from Attempt {target_hash}" in prompts[0]


def test_resume_from_resets_all_descendant_agent_worktrees(tmp_path: Path, monkeypatch) -> None:
    coral_dir = tmp_path / ".coral"
    agents_dir = tmp_path / "agents"
    repo_dir = tmp_path / "repo"
    agents_dir.mkdir()
    repo_dir.mkdir()

    base_repo = tmp_path / "base"
    base_repo.mkdir()
    _git(base_repo, "init")
    _git(base_repo, "config", "user.email", "test@example.com")
    _git(base_repo, "config", "user.name", "Test User")
    target_hash = _commit_file(base_repo, "solution.txt", "target\n", "target attempt")
    descendant_one = _commit_file(base_repo, "agent1.txt", "child\n", "agent 1 descendant")
    _git(base_repo, "checkout", "-b", "agent-2-branch", target_hash)
    descendant_two = _commit_file(base_repo, "agent2.txt", "child\n", "agent 2 descendant")
    _git(base_repo, "checkout", "--orphan", "unrelated")
    _git(base_repo, "rm", "-rf", ".")
    unrelated_hash = _commit_file(base_repo, "unrelated.txt", "other\n", "unrelated root")

    agent_dirs: dict[str, Path] = {}
    for agent_id, commit_hash in {
        "agent-1": descendant_one,
        "agent-2": descendant_two,
        "agent-3": unrelated_hash,
    }.items():
        agent_dir = agents_dir / agent_id
        _git(tmp_path, "clone", str(base_repo), str(agent_dir))
        _git(agent_dir, "checkout", "--detach", commit_hash)
        agent_dirs[agent_id] = agent_dir

    write_attempt(coral_dir, _attempt(target_hash))
    paths = ProjectPaths(
        results_dir=tmp_path,
        task_dir=tmp_path,
        run_dir=tmp_path,
        coral_dir=coral_dir,
        agents_dir=agents_dir,
        repo_dir=repo_dir,
    )
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "agents": {"count": 3, "runtime": "claude-code"},
        }
    )
    manager = AgentManager(cfg)
    handles = _stub_manager_for_resume(manager, monkeypatch, agent_dirs)

    manager.resume_all(paths, instruction="revisit this branch", resume_from=target_hash)

    assert _git(agent_dirs["agent-1"], "rev-parse", "HEAD") == target_hash
    assert _git(agent_dirs["agent-2"], "rev-parse", "HEAD") == target_hash
    assert _git(agent_dirs["agent-3"], "rev-parse", "HEAD") == unrelated_hash

    prompts = {h.agent_id: h.prompt for h in handles}
    assert f"## Continue from Attempt {target_hash}" in prompts["agent-1"]
    assert f"## Continue from Attempt {target_hash}" in prompts["agent-2"]
    assert f"## Continue from Attempt {target_hash}" not in prompts["agent-3"]
