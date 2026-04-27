"""Tests for the manager's seen-attempts initialization.

Regression: pending attempts left over from a previous manager (mid-grade
when we resumed) used to be captured in the initial `seen_attempts` set,
so when they later transitioned to scored they never appeared in
`new_attempts` and never triggered heartbeat. The fix initializes
`seen_attempts` to only the already-scored attempts so pending-at-startup
evals flow through the normal detection path.
"""

from __future__ import annotations

import json
from pathlib import Path

from coral.agent.manager import AgentManager
from coral.config import CoralConfig
from coral.workspace import ProjectPaths


def _build_manager_with_attempts(tmp_path: Path, attempts: dict[str, str]):
    """Spin up a manager with a fake attempts directory pre-populated."""
    coral_dir = tmp_path / ".coral"
    (coral_dir / "public" / "attempts").mkdir(parents=True)
    (coral_dir / "public" / "logs").mkdir()
    for name, status in attempts.items():
        path = coral_dir / "public" / "attempts" / f"{name}.json"
        path.write_text(json.dumps({"agent_id": "agent-1", "status": status}))

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
        "agents": {"runtime": "claude-code"},
    })
    manager = AgentManager(cfg, verbose=False)
    manager.paths = paths
    return manager, paths


def test_pending_at_startup_is_not_seen(tmp_path: Path) -> None:
    """Pending attempts at startup must NOT be in the initial seen set so
    heartbeat fires when they later transition to scored."""
    manager, _ = _build_manager_with_attempts(tmp_path, {
        "scored1": "improved",
        "scored2": "regressed",
        "pending1": "pending",
    })
    # This mirrors the initialization in monitor_loop: only already-scored
    # attempts are seen.
    seen = manager._filter_scored(manager._get_seen_attempts())
    assert "scored1.json" in seen
    assert "scored2.json" in seen
    assert "pending1.json" not in seen


def test_pending_then_scored_appears_as_new(tmp_path: Path) -> None:
    """A pending-at-startup attempt that later scores must be visible in
    `current - seen` so the dispatch path picks it up."""
    manager, paths = _build_manager_with_attempts(tmp_path, {
        "pending1": "pending",
    })
    seen = manager._filter_scored(manager._get_seen_attempts())
    assert seen == set()  # nothing scored yet

    # Simulate the grader daemon finalizing the attempt.
    pending_path = paths.coral_dir / "public" / "attempts" / "pending1.json"
    pending_path.write_text(json.dumps({"agent_id": "agent-1", "status": "improved"}))

    current = manager._get_seen_attempts()
    new = current - seen
    scored_new = manager._filter_scored(new)
    assert scored_new == {"pending1.json"}


def test_already_scored_at_startup_does_not_re_fire(tmp_path: Path) -> None:
    """Attempts that were already scored when the manager came up must
    not be in the post-startup new set — we don't want to re-dispatch
    heartbeat for historical evals."""
    manager, _ = _build_manager_with_attempts(tmp_path, {
        "scored1": "improved",
    })
    seen = manager._filter_scored(manager._get_seen_attempts())
    current = manager._get_seen_attempts()
    new = current - seen
    assert new == set()
