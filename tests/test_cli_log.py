"""Tests for `coral log` filtering behavior (issue #73)."""

import argparse
import tempfile
from pathlib import Path

import pytest

from coral.cli import query as query_module
from coral.cli.query import cmd_log
from coral.hub.attempts import write_attempt
from coral.types import Attempt


def _make(commit: str, score: float, budget_class: str = "real", title: str = "t") -> Attempt:
    return Attempt(
        commit_hash=commit,
        agent_id="agent-1",
        title=title,
        score=score,
        status="improved",
        parent_hash=None,
        timestamp="2026-03-11T10:00:00Z",
        metadata={"budget_class": budget_class},
    )


@pytest.fixture
def coral_dir_with_mixed_attempts(monkeypatch: pytest.MonkeyPatch):
    """Coral dir holding one attempt of each budget class."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        write_attempt(coral_dir, _make("aaa1", 0.9, "real", title="real-A"))
        write_attempt(coral_dir, _make("bbb2", 0.7, "real", title="real-B"))
        write_attempt(coral_dir, _make("ccc3", 0.5, "tune", title="tune-A"))
        write_attempt(coral_dir, _make("ddd4", 0.3, "grader_error", title="error-A"))

        monkeypatch.setattr(
            query_module,
            "find_coral_dir_and_island",
            lambda task=None, run=None: (coral_dir, None),
        )
        monkeypatch.setattr(query_module, "read_direction", lambda _coral_dir: "maximize")
        yield coral_dir


def _run_cmd_log(capsys: pytest.CaptureFixture, **flags) -> str:
    args = argparse.Namespace(
        count=20,
        recent=False,
        agent=None,
        search=None,
        all=False,
        budget_class=None,
        task=None,
        run=None,
    )
    for k, v in flags.items():
        setattr(args, k, v)
    cmd_log(args)
    return capsys.readouterr().out


def test_log_default_hides_tune_and_grader_error(coral_dir_with_mixed_attempts, capsys):
    """Default `coral log` shows only real attempts."""
    out = _run_cmd_log(capsys)
    assert "real-A" in out
    assert "real-B" in out
    assert "tune-A" not in out
    assert "error-A" not in out


def test_log_all_includes_tune_and_grader_error(coral_dir_with_mixed_attempts, capsys):
    """`coral log --all` shows everything regardless of budget class."""
    out = _run_cmd_log(capsys, all=True)
    assert "real-A" in out
    assert "real-B" in out
    assert "tune-A" in out
    assert "error-A" in out


def test_log_recent_filter_applies(coral_dir_with_mixed_attempts, capsys):
    """`coral log --recent` honors the same default filter."""
    out = _run_cmd_log(capsys, recent=True)
    assert "real-A" in out
    assert "tune-A" not in out


def test_log_search_filter_applies(coral_dir_with_mixed_attempts, capsys):
    """`coral log --search` honors the default filter — tune/error rows that
    match the search term are still hidden without --all."""
    # Search term matches only the tune row's title. Without --all, the
    # tune row gets filtered out, so the result is "No attempts matching".
    out = _run_cmd_log(capsys, search="tune-A")
    assert "No attempts matching" in out
    # With --all, the tune row's commit_hash shows up in the leaderboard.
    out_all = _run_cmd_log(capsys, search="tune-A", all=True)
    assert "ccc3" in out_all  # the tune row's commit hash


def test_log_agent_filter_applies(coral_dir_with_mixed_attempts, capsys):
    """`coral log --agent ...` honors the default filter."""
    out = _run_cmd_log(capsys, agent="agent-1")
    assert "real-A" in out
    assert "tune-A" not in out
    out_all = _run_cmd_log(capsys, agent="agent-1", all=True)
    assert "tune-A" in out_all


def test_log_class_tune_shows_only_tune(coral_dir_with_mixed_attempts, capsys):
    """`coral log --class tune` returns only tune-mode attempts."""
    out = _run_cmd_log(capsys, budget_class="tune")
    assert "tune-A" in out
    assert "real-A" not in out
    assert "real-B" not in out
    assert "error-A" not in out


def test_log_class_grader_error_shows_only_errors(coral_dir_with_mixed_attempts, capsys):
    """`coral log --class grader_error` returns only grader_error attempts."""
    out = _run_cmd_log(capsys, budget_class="grader_error")
    assert "error-A" in out
    assert "real-A" not in out
    assert "tune-A" not in out


def test_log_class_real_shows_only_real(coral_dir_with_mixed_attempts, capsys):
    """`coral log --class real` is equivalent to the default filter."""
    out = _run_cmd_log(capsys, budget_class="real")
    assert "real-A" in out
    assert "real-B" in out
    assert "tune-A" not in out
    assert "error-A" not in out


def test_log_class_composes_with_agent_filter(coral_dir_with_mixed_attempts, capsys):
    """`coral log --class tune --agent agent-1` narrows to that intersection."""
    out = _run_cmd_log(capsys, budget_class="tune", agent="agent-1")
    assert "tune-A" in out
    assert "real-A" not in out
