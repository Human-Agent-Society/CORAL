"""Tests for eval implementation and Claude Code settings."""

import json
import subprocess
import tempfile
from pathlib import Path

import yaml

from coral.hooks.post_commit import (
    run_eval,
    _increment_eval_count,
)
from coral.workspace.setup import setup_claude_settings


def _setup_repo_with_config(base_dir: Path) -> Path:
    """Create a git repo with .coral/config.yaml and return repo_path."""
    repo = base_dir / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test.com"], capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], capture_output=True)

    # Create a file and .gitignore, then make an initial commit
    (repo / "hello.py").write_text("print('hello')\n")
    (repo / ".gitignore").write_text(".coral/\n.coral_dir\n.claude/\n.coral_agent_id\nCLAUDE.md\ntest_grader_module.py\n")
    subprocess.run(["git", "-C", str(repo), "add", "hello.py", ".gitignore"], capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "Initial"], capture_output=True, check=True)

    # Set up .coral directory with config
    coral_dir = repo / ".coral"
    coral_dir.mkdir()
    (coral_dir / "public" / "attempts").mkdir(parents=True)

    # Write .coral_dir breadcrumb (as write_coral_dir does)
    (repo / ".coral_dir").write_text(str(coral_dir.resolve()))

    # Write a config that uses a simple function grader
    grader_module = repo / "test_grader_module.py"
    grader_module.write_text(
        "def grade(codebase_path, tasks):\n"
        "    return 0.75\n"
    )

    config = {
        "task": {"name": "test_task", "description": "A test"},
        "grader": {"type": "function", "module": "test_grader_module", "args": {"func_name": "grade"}},
        "agents": {"count": 1},
        "sharing": {"attempts": True, "notes": True, "skills": True},
        "workspace": {"base_dir": str(repo), "repo_path": str(repo)},
    }
    with open(coral_dir / "config.yaml", "w") as f:
        yaml.dump(config, f)

    return repo


def test_run_eval_with_function_grader():
    """Integration test: run_eval stages, commits, and grades."""
    import sys

    with tempfile.TemporaryDirectory() as d:
        repo = _setup_repo_with_config(Path(d))

        # Make a change that will be staged and committed by run_eval
        (repo / "hello.py").write_text("print('hello world')\n")

        # Add the repo to sys.path so the grader module can be imported
        sys.path.insert(0, str(repo))
        try:
            attempt = run_eval(message="Update hello message", agent_id="agent-test", workdir=str(repo))
        finally:
            sys.path.pop(0)

        assert attempt.agent_id == "agent-test"
        assert attempt.title == "Update hello message"
        assert attempt.score == 0.75
        assert attempt.status == "improved"
        assert attempt.commit_hash  # Should have a real commit hash

        # Check that attempt JSON was written
        attempt_file = repo / ".coral" / "public" / "attempts" / f"{attempt.commit_hash}.json"
        assert attempt_file.exists()
        data = json.loads(attempt_file.read_text())
        assert data["score"] == 0.75


def test_run_eval_no_changes():
    """run_eval should fail if there are no changes to commit."""
    import sys

    with tempfile.TemporaryDirectory() as d:
        repo = _setup_repo_with_config(Path(d))

        sys.path.insert(0, str(repo))
        try:
            attempt = run_eval(message="No changes", agent_id="agent-test", workdir=str(repo))
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "Nothing to commit" in str(e)
        finally:
            sys.path.pop(0)


def test_eval_count_and_reflection():
    """Test that eval count increments and reflection nudge triggers correctly."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "public").mkdir()

        # Counter starts at 0, increments to 1
        assert _increment_eval_count(coral_dir) == 1
        assert _increment_eval_count(coral_dir) == 2
        assert _increment_eval_count(coral_dir) == 3

        # Check file contents
        assert (coral_dir / "public" / "eval_count").read_text() == "3"


def test_run_eval_tracks_eval_count():
    """Integration: run_eval increments eval_count and sets reflection flag."""
    import sys

    with tempfile.TemporaryDirectory() as d:
        repo = _setup_repo_with_config(Path(d))

        sys.path.insert(0, str(repo))
        try:
            # First eval
            (repo / "hello.py").write_text("print('v1')\n")
            a1 = run_eval(message="v1", agent_id="agent-test", workdir=str(repo))
            assert getattr(a1, "_eval_count", None) == 1

            # Second eval
            (repo / "hello.py").write_text("print('v2')\n")
            a2 = run_eval(message="v2", agent_id="agent-test", workdir=str(repo))
            assert getattr(a2, "_eval_count", None) == 2
        finally:
            sys.path.pop(0)



# --- setup_claude_settings tests ---


def test_setup_claude_settings_permissions():
    """Settings should grant tool permissions."""
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d) / "worktree"
        worktree.mkdir()
        coral_dir = Path(d) / ".coral"
        (coral_dir / "private").mkdir(parents=True)
        (coral_dir / "public").mkdir(parents=True)

        setup_claude_settings(worktree, coral_dir)

        settings = json.loads((worktree / ".claude" / "settings.json").read_text())
        private_dir = str(coral_dir.resolve() / "private")

        worktree_str = str(worktree.resolve())
        agents_dir = str(coral_dir.resolve().parent / "agents")

        # No sandbox
        assert "sandbox" not in settings

        # Permission allow rules grant agent autonomy
        allow = settings["permissions"]["allow"]
        # Bash/Read/Edit/Write scoped to own worktree (Read also allows agents dir)
        assert any("Bash" in r and worktree_str in r for r in allow)
        assert any("Read" in r and worktree_str in r for r in allow)
        assert any("Read" in r and agents_dir in r for r in allow)
        assert "Read" not in allow  # no blanket Read
        assert any("Edit" in r and worktree_str in r for r in allow)
        assert any("Write" in r and worktree_str in r for r in allow)
        assert "WebSearch" in allow  # research=True by default
        assert "WebFetch" in allow

        # Permission deny rules block git and private dir
        deny = settings["permissions"]["deny"]
        assert "Bash(git *)" in deny
        assert any(private_dir in r for r in deny)
        assert not any("WebSearch" in r for r in deny)

        assert "hooks" not in settings


def test_setup_claude_settings_no_research():
    """Settings should deny WebSearch/WebFetch when research=False."""
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d) / "worktree"
        worktree.mkdir()
        coral_dir = Path(d) / ".coral"
        (coral_dir / "private").mkdir(parents=True)
        (coral_dir / "public").mkdir(parents=True)

        setup_claude_settings(worktree, coral_dir, research=False)

        settings = json.loads((worktree / ".claude" / "settings.json").read_text())
        allow = settings["permissions"]["allow"]
        deny = settings["permissions"]["deny"]

        assert "WebSearch" not in allow
        assert "WebFetch" not in allow
        assert "WebSearch" in deny
        assert "WebFetch" in deny
