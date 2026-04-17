"""Tests for eval implementation and Claude Code settings."""

import json
import subprocess
import tempfile
from pathlib import Path

import yaml

from coral.grader.daemon import process_pending_once
from coral.hooks.post_commit import (
    _increment_eval_count,
    submit_eval,
)
from coral.workspace import setup_claude_settings


def _submit_and_grade(message: str, agent_id: str, workdir: str):
    """Submit a pending attempt, then synchronously drain the grader queue.

    Mirrors the production flow (submit + async grader + wait) without
    needing to spawn a separate grader daemon process in tests.
    """
    from coral.hooks.post_commit import _find_coral_dir
    from coral.hub.attempts import read_attempt, read_eval_count

    # Stage+commit+write pending; no wait because there's no daemon running.
    pending = submit_eval(message=message, agent_id=agent_id, workdir=workdir, wait=False)

    coral_dir = _find_coral_dir(Path(workdir).resolve())
    assert coral_dir is not None
    process_pending_once(coral_dir)

    final = read_attempt(coral_dir, pending.commit_hash)
    assert final is not None
    try:
        final._eval_count = read_eval_count(coral_dir)  # type: ignore[attr-defined]
    except Exception:
        pass
    return final


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


def test_submit_eval_pending_then_graded():
    """submit_eval writes a pending record; daemon finalizes it with a score."""
    import sys

    with tempfile.TemporaryDirectory() as d:
        repo = _setup_repo_with_config(Path(d))

        (repo / "hello.py").write_text("print('hello world')\n")

        sys.path.insert(0, str(repo))
        try:
            # Stage without running grader yet.
            pending = submit_eval(
                message="Update hello message",
                agent_id="agent-test",
                workdir=str(repo),
                wait=False,
            )
            assert pending.status == "pending"
            assert pending.score is None

            attempt_file = repo / ".coral" / "public" / "attempts" / f"{pending.commit_hash}.json"
            assert attempt_file.exists()
            pending_data = json.loads(attempt_file.read_text())
            assert pending_data["status"] == "pending"
            assert pending_data["score"] is None

            # Drain the grader queue synchronously.
            process_pending_once(repo / ".coral")

            final_data = json.loads(attempt_file.read_text())
            assert final_data["score"] == 0.75
            assert final_data["status"] == "improved"
            assert final_data["commit_hash"] == pending.commit_hash
        finally:
            sys.path.pop(0)


def test_submit_eval_no_changes():
    """submit_eval should fail if there are no changes to commit."""
    import sys

    with tempfile.TemporaryDirectory() as d:
        repo = _setup_repo_with_config(Path(d))

        sys.path.insert(0, str(repo))
        try:
            submit_eval(
                message="No changes",
                agent_id="agent-test",
                workdir=str(repo),
                wait=False,
            )
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "Nothing to commit" in str(e)
        finally:
            sys.path.pop(0)


def test_eval_count_and_reflection():
    """Test that eval count increments."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "public").mkdir()

        # Counter starts at 0, increments to 1
        assert _increment_eval_count(coral_dir) == 1
        assert _increment_eval_count(coral_dir) == 2
        assert _increment_eval_count(coral_dir) == 3

        # Check file contents
        assert (coral_dir / "public" / "eval_count").read_text() == "3"


def test_submit_eval_tracks_eval_count():
    """Integration: daemon bumps the eval counter when finalizing attempts."""
    import sys

    with tempfile.TemporaryDirectory() as d:
        repo = _setup_repo_with_config(Path(d))

        sys.path.insert(0, str(repo))
        try:
            (repo / "hello.py").write_text("print('v1')\n")
            a1 = _submit_and_grade("v1", "agent-test", str(repo))
            assert getattr(a1, "_eval_count", None) == 1

            (repo / "hello.py").write_text("print('v2')\n")
            a2 = _submit_and_grade("v2", "agent-test", str(repo))
            assert getattr(a2, "_eval_count", None) == 2
        finally:
            sys.path.pop(0)


def test_submit_eval_sets_shared_state_hash():
    """submit_eval should checkpoint shared state and store hash in the attempt.

    The checkpoint runs before write_attempt, so the first eval has no prior
    shared state changes (hash is None). The second eval sees the first eval's
    attempt JSON and eval_count, producing a non-None hash.
    """
    import sys

    with tempfile.TemporaryDirectory() as d:
        repo = _setup_repo_with_config(Path(d))

        sys.path.insert(0, str(repo))
        try:
            # First eval — no prior shared state changes, hash should be None
            (repo / "hello.py").write_text("print('v1')\n")
            a1 = _submit_and_grade("first", "agent-test", str(repo))
            assert a1.shared_state_hash is None

            # Second eval — first eval wrote attempt JSON + eval_count, so checkpoint finds changes
            (repo / "hello.py").write_text("print('v2')\n")
            a2 = _submit_and_grade("second", "agent-test", str(repo))
            assert a2.shared_state_hash is not None
            assert len(a2.shared_state_hash) == 40
            # Parent shared state hash comes from the first attempt
            assert a2.parent_shared_state_hash == a1.shared_state_hash

            # Verify hashes were persisted in the attempt JSON
            attempt_file = repo / ".coral" / "public" / "attempts" / f"{a2.commit_hash}.json"
            data = json.loads(attempt_file.read_text())
            assert data["shared_state_hash"] == a2.shared_state_hash
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

        settings = json.loads((worktree / ".claude" / "settings.local.json").read_text())
        private_dir = str(coral_dir.resolve() / "private")

        worktree_str = str(worktree.resolve())
        agents_dir = str(coral_dir.resolve().parent / "agents")

        # No sandbox
        assert "sandbox" not in settings

        # Permission allow rules grant agent autonomy
        allow = settings["permissions"]["allow"]
        # Bash is unscoped; Read/Edit/Write scoped to own worktree
        assert "Bash" in allow
        assert any("Read" in r and worktree_str in r for r in allow)
        assert any("Read" in r and agents_dir in r for r in allow)
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

        # Auto mode is always enabled
        assert settings["permissions"]["defaultMode"] == "auto"


def test_setup_claude_settings_no_research():
    """Settings should deny WebSearch/WebFetch when research=False."""
    with tempfile.TemporaryDirectory() as d:
        worktree = Path(d) / "worktree"
        worktree.mkdir()
        coral_dir = Path(d) / ".coral"
        (coral_dir / "private").mkdir(parents=True)
        (coral_dir / "public").mkdir(parents=True)

        setup_claude_settings(worktree, coral_dir, research=False)

        settings = json.loads((worktree / ".claude" / "settings.local.json").read_text())
        allow = settings["permissions"]["allow"]
        deny = settings["permissions"]["deny"]

        assert "WebSearch" not in allow
        assert "WebFetch" not in allow
        assert "WebSearch" in deny
        assert "WebFetch" in deny
