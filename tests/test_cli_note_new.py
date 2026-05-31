"""End-to-end test for `coral note new <slug>`."""

import os
import subprocess


def test_note_new_stamps_creator_and_created(tmp_path):
    """`coral note new <slug>` writes a note with `creator:` + `created:` stamped."""
    coral_dir = tmp_path / ".coral"
    (coral_dir / "public" / "notes").mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    # Single-island breadcrumbs
    (worktree / ".coral_dir").write_text(str(coral_dir.resolve()))
    (worktree / ".coral_agent_id").write_text("agent-7")

    env = os.environ.copy()
    result = subprocess.run(
        ["coral", "note", "new", "my-finding", "--body", "First-line summary."],
        cwd=str(worktree),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    note_path = coral_dir / "public" / "notes" / "my-finding.md"
    assert note_path.exists()
    text = note_path.read_text()
    assert text.startswith("---")
    assert "creator: agent-7" in text
    assert "created:" in text
    assert "First-line summary." in text


def test_note_new_writes_to_island_in_multi_island(tmp_path):
    """In multi-island mode, the note lands in islands/<id>/notes/."""
    coral_dir = tmp_path / ".coral"
    (coral_dir / "islands" / "1" / "notes").mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".coral_dir").write_text(str(coral_dir.resolve()))
    (worktree / ".coral_agent_id").write_text("0-agent-2")
    (worktree / ".coral_island").write_text("1")

    env = os.environ.copy()
    result = subprocess.run(
        ["coral", "note", "new", "moved-and-found", "--body", "body"],
        cwd=str(worktree),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    note_path = coral_dir / "islands" / "1" / "notes" / "moved-and-found.md"
    assert note_path.exists()
    assert "creator: 0-agent-2" in note_path.read_text()
