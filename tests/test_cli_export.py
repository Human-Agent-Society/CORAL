"""`coral export` — turn an attempt commit into a normal git branch."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from coral.cli import eval as eval_cli
from coral.hub.attempts import write_attempt
from coral.types import Attempt


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _make_run(tmp_path: Path) -> tuple[Path, Path, str]:
    """Build a run layout with a real commit; return (coral_dir, repo, hash)."""
    run_dir = tmp_path / "results" / "task" / "ts"
    coral_dir = run_dir / ".coral"
    (coral_dir / "public" / "attempts").mkdir(parents=True)

    repo = run_dir / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "f.txt").write_text("hi")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "exp")
    commit = _git(repo, "rev-parse", "HEAD")

    write_attempt(
        coral_dir,
        Attempt(
            commit_hash=commit,
            agent_id="agent-1",
            title="exp",
            score=0.5,
            status="improved",
            parent_hash=None,
            timestamp="2026-06-01T10:00:00Z",
        ),
    )
    return coral_dir, repo, commit


def _args(**kw):
    base = {"task": None, "run": None, "force": False}
    base.update(kw)
    return SimpleNamespace(**base)


def test_export_creates_branch(tmp_path, monkeypatch):
    coral_dir, repo, commit = _make_run(tmp_path)
    monkeypatch.setattr(eval_cli, "find_coral_dir_and_island", lambda *a, **k: (coral_dir, None))

    eval_cli.cmd_export(_args(hash=commit, branch="coral/best"))

    assert _git(repo, "rev-parse", "coral/best") == commit


def test_export_unknown_hash_exits(tmp_path, monkeypatch):
    coral_dir, repo, _ = _make_run(tmp_path)
    monkeypatch.setattr(eval_cli, "find_coral_dir_and_island", lambda *a, **k: (coral_dir, None))

    with pytest.raises(SystemExit):
        eval_cli.cmd_export(_args(hash="deadbeef", branch="x"))


def test_export_existing_branch_requires_force(tmp_path, monkeypatch):
    coral_dir, repo, commit = _make_run(tmp_path)
    monkeypatch.setattr(eval_cli, "find_coral_dir_and_island", lambda *a, **k: (coral_dir, None))
    eval_cli.cmd_export(_args(hash=commit, branch="dup"))

    with pytest.raises(SystemExit):
        eval_cli.cmd_export(_args(hash=commit, branch="dup"))

    # --force overwrites instead of failing.
    eval_cli.cmd_export(_args(hash=commit, branch="dup", force=True))
    assert _git(repo, "rev-parse", "dup") == commit
