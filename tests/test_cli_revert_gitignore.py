"""Test that coral revert/checkout preserve .gitignore CORAL entries."""

import subprocess
from pathlib import Path

import pytest


def _git(workdir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(workdir),
        capture_output=True,
        text=True,
        check=True,
        env={"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"},
    )


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    """Create a git repo simulating post-seed state with breadcrumb files."""
    repo = tmp_path / "repo"
    repo.mkdir()

    _git(repo, "init")
    # Seed commit: .gitignore without CORAL entries (mimics user's repo)
    gitignore = repo / ".gitignore"
    gitignore.write_text("build/\n*.o\n")
    (repo / "main.cpp").write_text("int main() {}")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed commit")

    # Simulate CORAL setup_gitignore (appends entries to working tree)
    from coral.workspace.worktree import setup_gitignore
    setup_gitignore(repo)

    # Simulate CORAL writing breadcrumb files
    (repo / ".coral_agent_id").write_text("captain-nemo")
    (repo / ".coral_dir").write_text("/tmp/coral")

    # Agent's first eval: makes a code change and commits
    (repo / "main.cpp").write_text("int main() { return 0; }")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "attempt 1")

    return repo


def test_revert_preserves_gitignore(worktree: Path):
    """After coral revert, .gitignore still has CORAL entries."""
    from coral.workspace.worktree import setup_gitignore
    from unittest.mock import patch
    import argparse

    from coral.cli.eval import cmd_revert

    args = argparse.Namespace(workdir=str(worktree))
    cmd_revert(args)

    gitignore = (worktree / ".gitignore").read_text()
    assert ".coral_agent_id" in gitignore
    assert ".coral_dir" in gitignore
    assert "CLAUDE.md" in gitignore


def test_revert_breadcrumbs_not_staged(worktree: Path):
    """After coral revert, git add -A does not stage breadcrumb files."""
    import argparse

    from coral.cli.eval import cmd_revert

    args = argparse.Namespace(workdir=str(worktree))
    cmd_revert(args)

    # Simulate what coral eval does
    _git(worktree, "add", "-A")
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(worktree),
        capture_output=True,
        text=True,
    )
    staged_files = result.stdout
    assert ".coral_agent_id" not in staged_files
    assert ".coral_dir" not in staged_files


def test_without_fix_breadcrumbs_would_be_staged(tmp_path: Path):
    """Demonstrates the bug: without setup_gitignore after reset, breadcrumbs get staged."""
    repo = tmp_path / "repo"
    repo.mkdir()

    _git(repo, "init")
    gitignore = repo / ".gitignore"
    gitignore.write_text("build/\n*.o\n")
    (repo / "main.cpp").write_text("int main() {}")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed commit")

    # CORAL setup appends to .gitignore (working tree only)
    from coral.workspace.worktree import setup_gitignore
    setup_gitignore(repo)

    # Breadcrumb files created
    (repo / ".coral_agent_id").write_text("captain-nemo")
    (repo / ".coral_dir").write_text("/tmp/coral")

    # Agent commits
    (repo / "main.cpp").write_text("int main() { return 0; }")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "attempt 1")

    # Raw reset (what coral revert did BEFORE the fix)
    _git(repo, "reset", "--hard", "HEAD~1")

    # .gitignore is now reverted to committed state (no CORAL entries)
    gitignore_content = gitignore.read_text()
    assert ".coral_agent_id" not in gitignore_content, "Expected entries to be lost after reset"

    # git add -A would stage the breadcrumb files
    _git(repo, "add", "-A")
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    # .coral_agent_id shows up as a new untracked file being staged
    assert ".coral_agent_id" in result.stdout, "Bug demo: breadcrumb should be staged without fix"
