"""Tests for workspace setup."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from coral.config import AgentConfig, CoralConfig, GraderConfig, TaskConfig, WorkspaceConfig
from coral.workspace import (
    create_project,
    setup_gitignore,
    setup_worktree_env,
    write_agent_id,
)


def _make_config(repo_path: str, results_dir: str | None = None) -> CoralConfig:
    return CoralConfig(
        task=TaskConfig(name="Test Task", description="Test task"),
        grader=GraderConfig(type="function"),
        agents=AgentConfig(count=2),
        workspace=WorkspaceConfig(
            results_dir=results_dir or os.path.join(repo_path, "results"),
            repo_path=repo_path,
        ),
    )


def _git_init(d: str) -> None:
    """Initialise a git repo with a dummy commit (works without global config)."""
    subprocess.run(["git", "init", d], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", d, "-c", "user.name=test", "-c", "user.email=test@test.com",
         "commit", "--allow-empty", "-m", "init"],
        capture_output=True, check=True,
    )


def test_create_project_structure():
    with tempfile.TemporaryDirectory() as d:
        # Init a git repo so workspace can create worktrees
        _git_init(d)

        config = _make_config(d)
        paths = create_project(config)

        assert paths.run_dir.exists()
        assert paths.task_dir.exists()
        assert paths.coral_dir.exists()
        assert (paths.coral_dir / "public").is_dir()
        assert (paths.coral_dir / "public" / "attempts").is_dir()
        assert (paths.coral_dir / "public" / "logs").is_dir()
        assert (paths.coral_dir / "public" / "skills").is_dir()
        assert (paths.coral_dir / "public" / "notes").is_dir()
        assert (paths.coral_dir / "private").is_dir()
        assert (paths.coral_dir / "config.yaml").is_file()
        assert paths.agents_dir.exists()
        # Structure: results/<task-slug>/<timestamp>/
        assert "test-task" in str(paths.task_dir)
        # latest symlink
        latest = paths.task_dir / "latest"
        assert latest.is_symlink()


def test_create_project_unique_runs():
    """Each create_project call gets a unique run directory."""
    with tempfile.TemporaryDirectory() as d:
        _git_init(d)

        config = _make_config(d)
        paths1 = create_project(config)

        import time
        time.sleep(1.1)  # ensure different timestamp

        paths2 = create_project(config)

        assert paths1.run_dir != paths2.run_dir
        assert paths1.coral_dir != paths2.coral_dir
        # latest should point to the second run directory
        latest = paths1.task_dir / "latest"
        assert latest.resolve() == paths2.run_dir.resolve()


def test_write_agent_id():
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d)
        write_agent_id(worktree, "agent-42")
        content = (worktree / ".coral_agent_id").read_text()
        assert content == "agent-42"


def test_setup_gitignore():
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d)
        setup_gitignore(worktree)

        gitignore = worktree / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text()
        assert ".coral_agent_id" in content
        assert "CLAUDE.md" in content
        assert ".claude/" in content


def test_setup_gitignore_preserves_existing():
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d)
        gitignore = worktree / ".gitignore"
        gitignore.write_text("*.pyc\n__pycache__/\n")

        setup_gitignore(worktree)

        content = gitignore.read_text()
        assert "*.pyc" in content
        assert ".coral_agent_id" in content
        assert ".claude/" in content


def test_setup_gitignore_idempotent():
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d)
        setup_gitignore(worktree)
        setup_gitignore(worktree)

        content = (worktree / ".gitignore").read_text()
        assert content.count(".claude/") == 1


def test_create_project_runs_setup_commands():
    """Setup commands execute in the worktree directory."""
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d) / "worktree"
        worktree.mkdir()

        setup_worktree_env(worktree, ["echo hello > setup_marker.txt"])

        marker = worktree / "setup_marker.txt"
        assert marker.exists()
        assert marker.read_text().strip() == "hello"


def test_create_project_setup_command_failure():
    """A failing setup command raises RuntimeError."""
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d) / "worktree"
        worktree.mkdir()

        with pytest.raises(RuntimeError, match="Setup command failed"):
            setup_worktree_env(worktree, ["exit 1"])


def test_create_project_setup_runs_sequentially():
    """Setup commands run in order so later commands can depend on earlier ones."""
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d) / "worktree"
        worktree.mkdir()

        setup_worktree_env(worktree, [
            "mkdir -p mydir",
            "echo done > mydir/result.txt",
        ])

        result_file = worktree / "mydir" / "result.txt"
        assert result_file.exists()
        assert result_file.read_text().strip() == "done"


