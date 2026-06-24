"""Tests for run-level auto-stop decisions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from coral.agent.manager import AgentManager
from coral.config import CoralConfig
from coral.hub.attempts import write_attempt
from coral.hub.auto_stop import read_auto_stop
from coral.types import BUDGET_CLASS_GRADER_ERROR, BUDGET_CLASS_TUNE, Attempt
from coral.workspace import ProjectPaths


def _manager(
    tmp_path: Path,
    *,
    stop: dict[str, object],
    direction: str = "maximize",
) -> AgentManager:
    coral_dir = tmp_path / ".coral"
    (coral_dir / "public" / "attempts").mkdir(parents=True)
    (coral_dir / "public" / "logs").mkdir()
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "grader": {"direction": direction},
            "run": {"stop": stop},
        }
    )
    mgr = AgentManager(cfg, verbose=False)
    mgr.paths = ProjectPaths(
        results_dir=tmp_path / "results",
        task_dir=tmp_path,
        run_dir=tmp_path,
        coral_dir=coral_dir,
        agents_dir=tmp_path / "agents",
        repo_dir=tmp_path / "repo",
    )
    return mgr


def _attempt(
    mgr: AgentManager,
    commit: str,
    *,
    score: float | None,
    status: str = "improved",
    budget_class: str | None = None,
    seconds: int = 0,
) -> Attempt:
    assert mgr.paths is not None
    metadata = {"budget_class": budget_class} if budget_class else {}
    attempt = Attempt(
        commit_hash=commit,
        agent_id="agent-1",
        title=f"attempt {commit}",
        score=score,
        status=status,
        parent_hash=None,
        timestamp=(datetime(2026, 6, 24, tzinfo=UTC) + timedelta(seconds=seconds)).isoformat(),
        metadata=metadata,
    )
    write_attempt(mgr.paths.coral_dir, attempt)
    return attempt


def test_auto_stop_score_threshold_maximize(tmp_path: Path) -> None:
    mgr = _manager(tmp_path, stop={"score_threshold": 0.8})
    attempt = _attempt(mgr, "a" * 40, score=0.81)

    reason = mgr._auto_stop_reason_from_attempt(attempt.to_dict())

    assert reason is not None
    assert reason["reason"] == "score_threshold"
    assert reason["attempt_id"] == attempt.commit_hash
    assert reason["score"] == 0.81
    assert reason["score_threshold"] == 0.8
    assert reason["direction"] == "maximize"
    assert reason["real_attempt_count"] == 1


def test_auto_stop_score_threshold_minimize(tmp_path: Path) -> None:
    mgr = _manager(tmp_path, stop={"score_threshold": 0.2}, direction="minimize")
    attempt = _attempt(mgr, "b" * 40, score=0.19)

    reason = mgr._auto_stop_reason_from_attempt(attempt.to_dict())

    assert reason is not None
    assert reason["reason"] == "score_threshold"
    assert reason["direction"] == "minimize"
    assert reason["score"] == 0.19


def test_auto_stop_counts_only_terminal_real_attempts(tmp_path: Path) -> None:
    mgr = _manager(tmp_path, stop={"score_threshold": 0.8, "max_real_attempts": 2})
    _attempt(mgr, "c" * 40, score=0.99, budget_class=BUDGET_CLASS_TUNE, seconds=1)
    _attempt(mgr, "d" * 40, score=0.99, budget_class=BUDGET_CLASS_GRADER_ERROR, seconds=2)
    _attempt(mgr, "e" * 40, score=None, status="pending", seconds=3)
    _attempt(mgr, "f" * 40, score=None, status="crashed", seconds=4)
    latest_real = _attempt(mgr, "1" * 40, score=0.2, seconds=5)

    reason = mgr._auto_stop_reason_from_attempt(latest_real.to_dict())

    assert reason is not None
    assert reason["reason"] == "max_real_attempts"
    assert reason["real_attempt_count"] == 2
    assert reason["attempt_id"] == latest_real.commit_hash


def test_auto_stop_current_state_uses_best_real_attempt(tmp_path: Path) -> None:
    mgr = _manager(tmp_path, stop={"score_threshold": 0.8})
    _attempt(mgr, "2" * 40, score=0.99, budget_class=BUDGET_CLASS_TUNE, seconds=1)
    real = _attempt(mgr, "3" * 40, score=0.85, seconds=2)

    reason = mgr._auto_stop_reason_from_current_state()

    assert reason is not None
    assert reason["reason"] == "score_threshold"
    assert reason["attempt_id"] == real.commit_hash
    assert reason["score"] == 0.85
    assert reason["real_attempt_count"] == 1


def test_auto_stop_writes_marker_and_stops(tmp_path: Path) -> None:
    mgr = _manager(tmp_path, stop={"max_real_attempts": 1})
    attempt = _attempt(mgr, "4" * 40, score=0.1)
    reason = mgr._auto_stop_reason_from_attempt(attempt.to_dict())
    assert reason is not None

    mgr._running = True
    mgr._auto_stop(reason)

    assert mgr._running is False
    assert mgr._stopping is True
    marker = read_auto_stop(mgr.paths.coral_dir)
    assert marker is not None
    assert marker["reason"] == "max_real_attempts"
    assert marker["attempt_id"] == attempt.commit_hash
