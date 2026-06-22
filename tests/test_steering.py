"""Steer-on-resume queue and dashboard endpoint behavior."""

from __future__ import annotations

import json
import os
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
