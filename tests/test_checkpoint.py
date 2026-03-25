"""Tests for shared state checkpointing."""

import subprocess
import tempfile
from pathlib import Path

from coral.hub.checkpoint import (
    checkpoint,
    checkpoint_diff,
    checkpoint_history,
    init_checkpoint_repo,
)


def _make_coral_dir(tmp: Path) -> Path:
    """Create a minimal .coral/public/ structure."""
    coral_dir = tmp / ".coral"
    (coral_dir / "public" / "notes").mkdir(parents=True)
    (coral_dir / "public" / "attempts").mkdir(parents=True)
    return coral_dir


def test_init_checkpoint_repo():
    with tempfile.TemporaryDirectory() as tmp:
        coral_dir = _make_coral_dir(Path(tmp))
        init_checkpoint_repo(str(coral_dir))

        public = coral_dir / "public"
        assert (public / ".git").is_dir()
        assert (public / ".gitignore").read_text() == "coral.lock\n"

        # Verify initial commit exists
        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=str(public), capture_output=True, text=True,
        )
        assert "init: shared state tracking" in result.stdout


def test_init_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        coral_dir = _make_coral_dir(Path(tmp))
        init_checkpoint_repo(str(coral_dir))
        init_checkpoint_repo(str(coral_dir))  # should not raise

        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=str(coral_dir / "public"), capture_output=True, text=True,
        )
        # Only one commit from init
        lines = [line for line in result.stdout.strip().splitlines() if line]
        assert len(lines) == 1


def test_checkpoint_with_changes():
    with tempfile.TemporaryDirectory() as tmp:
        coral_dir = _make_coral_dir(Path(tmp))
        init_checkpoint_repo(str(coral_dir))

        # Write a note file
        (coral_dir / "public" / "notes" / "idea.md").write_text("# My idea\nTest content\n")

        commit_hash = checkpoint(str(coral_dir), "agent-1", "added a note")
        assert commit_hash is not None
        assert len(commit_hash) == 40  # full SHA


def test_checkpoint_no_changes():
    with tempfile.TemporaryDirectory() as tmp:
        coral_dir = _make_coral_dir(Path(tmp))
        init_checkpoint_repo(str(coral_dir))

        result = checkpoint(str(coral_dir), "agent-1", "nothing changed")
        assert result is None


def test_checkpoint_lazy_init():
    """checkpoint() should auto-init if .git is missing."""
    with tempfile.TemporaryDirectory() as tmp:
        coral_dir = _make_coral_dir(Path(tmp))
        # Don't call init_checkpoint_repo — checkpoint should lazy-init
        # First call inits (existing files get committed in init), returns None (no new changes)
        (coral_dir / "public" / "notes" / "note.md").write_text("test\n")
        checkpoint(str(coral_dir), "agent-1", "lazy init")
        assert (coral_dir / "public" / ".git").is_dir()

        # Second call with new changes should return a hash
        (coral_dir / "public" / "notes" / "note2.md").write_text("more\n")
        commit_hash = checkpoint(str(coral_dir), "agent-1", "lazy init test")
        assert commit_hash is not None


def test_checkpoint_history():
    with tempfile.TemporaryDirectory() as tmp:
        coral_dir = _make_coral_dir(Path(tmp))
        init_checkpoint_repo(str(coral_dir))

        # Create two checkpoints
        (coral_dir / "public" / "notes" / "a.md").write_text("first\n")
        checkpoint(str(coral_dir), "agent-1", "first change")

        (coral_dir / "public" / "notes" / "b.md").write_text("second\n")
        checkpoint(str(coral_dir), "agent-2", "second change")

        history = checkpoint_history(str(coral_dir))
        assert len(history) == 3  # 2 checkpoints + 1 init
        assert "agent-2" in history[0]["message"]
        assert "agent-1" in history[1]["message"]
        assert "init" in history[2]["message"]


def test_checkpoint_history_empty():
    with tempfile.TemporaryDirectory() as tmp:
        coral_dir = _make_coral_dir(Path(tmp))
        # No repo at all
        history = checkpoint_history(str(coral_dir))
        assert history == []


def test_checkpoint_diff():
    with tempfile.TemporaryDirectory() as tmp:
        coral_dir = _make_coral_dir(Path(tmp))
        init_checkpoint_repo(str(coral_dir))

        (coral_dir / "public" / "notes" / "x.md").write_text("hello\n")
        commit_hash = checkpoint(str(coral_dir), "agent-1", "add x")
        assert commit_hash is not None

        diff_output = checkpoint_diff(str(coral_dir), commit_hash)
        assert "x.md" in diff_output
        assert "hello" in diff_output


def test_checkpoint_diff_no_repo():
    with tempfile.TemporaryDirectory() as tmp:
        coral_dir = _make_coral_dir(Path(tmp))
        result = checkpoint_diff(str(coral_dir), "deadbeef")
        assert "No checkpoint repo" in result


def test_checkpoint_diff_bad_hash():
    with tempfile.TemporaryDirectory() as tmp:
        coral_dir = _make_coral_dir(Path(tmp))
        init_checkpoint_repo(str(coral_dir))

        result = checkpoint_diff(str(coral_dir), "0000000000000000000000000000000000000000")
        assert "Failed" in result
