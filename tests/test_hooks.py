"""Tests for eval implementation and workspace guard hook."""

import json
import subprocess
import tempfile
from pathlib import Path

import yaml

from coral.hooks.post_commit import (
    run_eval,
    _increment_eval_count,
)
from coral.config import CoralConfig, GraderConfig, TaskConfig
from coral.hooks.workspace_guard import _is_under, _resolve


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


# --- Workspace guard tests ---


def _run_guard(tool_name: str, tool_input: dict, cwd: str, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Invoke the workspace_guard hook as a subprocess."""
    import sys

    hook_input = json.dumps({
        "tool_name": tool_name,
        "tool_input": tool_input,
        "cwd": cwd,
    })
    cmd = [sys.executable, "-m", "coral.hooks.workspace_guard"]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(
        cmd,
        input=hook_input,
        capture_output=True,
        text=True,
    )


def test_workspace_guard_allows_own_worktree():
    """Guard should allow file operations within the agent's worktree."""
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d) / "worktree"
        worktree.mkdir()
        (worktree / "main.py").write_text("x = 1\n")

        result = _run_guard("Read", {"file_path": str(worktree / "main.py")}, str(worktree))
        assert result.returncode == 0


def test_workspace_guard_allows_read_sibling_worktree():
    """Guard should allow read-only access to sibling agent worktrees."""
    with tempfile.TemporaryDirectory() as d:
        wt1 = Path(d) / "agents" / "agent-1"
        wt2 = Path(d) / "agents" / "agent-2"
        wt1.mkdir(parents=True)
        wt2.mkdir(parents=True)
        (wt2 / "main.py").write_text("x = 2\n")

        result = _run_guard("Read", {"file_path": str(wt2 / "main.py")}, str(wt1))
        assert result.returncode == 0


def test_workspace_guard_blocks_write_other_worktree():
    """Guard should block write operations targeting another agent's worktree."""
    with tempfile.TemporaryDirectory() as d:
        wt1 = Path(d) / "agents" / "agent-1"
        wt2 = Path(d) / "agents" / "agent-2"
        wt1.mkdir(parents=True)
        wt2.mkdir(parents=True)
        (wt2 / "main.py").write_text("x = 2\n")

        result = _run_guard("Write", {"file_path": str(wt2 / "main.py")}, str(wt1))
        assert result.returncode == 2
        assert "outside your workspace" in result.stderr


def test_workspace_guard_allows_coral_public():
    """Guard should allow reading from .coral/public/ via breadcrumb."""
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d) / "worktree"
        worktree.mkdir()
        coral_dir = Path(d) / ".coral"
        (coral_dir / "public" / "notes").mkdir(parents=True)
        (coral_dir / "public" / "notes" / "note.md").write_text("insight")

        # Write .coral_dir breadcrumb
        (worktree / ".coral_dir").write_text(str(coral_dir))

        result = _run_guard(
            "Read",
            {"file_path": str(coral_dir / "public" / "notes" / "note.md")},
            str(worktree),
        )
        assert result.returncode == 0


def test_workspace_guard_blocks_coral_private():
    """Guard should block reading from .coral/private/ via absolute path."""
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d) / "worktree"
        worktree.mkdir()
        coral_dir = Path(d) / ".coral"
        (coral_dir / "private").mkdir(parents=True)
        (coral_dir / "private" / "secret.txt").write_text("secret")

        # .coral_dir breadcrumb points to the shared .coral directory
        (worktree / ".coral_dir").write_text(str(coral_dir))

        result = _run_guard(
            "Read",
            {"file_path": str(coral_dir / "private" / "secret.txt")},
            str(worktree),
        )
        assert result.returncode == 2
        assert "private" in result.stderr


def test_workspace_guard_blocks_web_without_research():
    """Guard should block WebSearch when --research is not enabled."""
    with tempfile.TemporaryDirectory() as d:
        result = _run_guard("WebSearch", {"query": "hello"}, d)
        assert result.returncode == 2
        assert "not allowed" in result.stderr


def test_workspace_guard_allows_web_with_research():
    """Guard should allow WebSearch when --research is enabled."""
    with tempfile.TemporaryDirectory() as d:
        result = _run_guard("WebSearch", {"query": "hello"}, d, extra_args=["--research"])
        assert result.returncode == 0


def test_workspace_guard_allows_non_file_tools():
    """Guard should allow tools that are not file, bash, or web tools."""
    with tempfile.TemporaryDirectory() as d:
        result = _run_guard("AskUserQuestion", {"question": "hello?"}, d)
        assert result.returncode == 0


def test_workspace_guard_allows_glob_without_path():
    """Guard should allow Glob/Grep when no path is specified (defaults to cwd)."""
    with tempfile.TemporaryDirectory() as d:
        result = _run_guard("Glob", {"pattern": "*.py"}, d)
        assert result.returncode == 0
