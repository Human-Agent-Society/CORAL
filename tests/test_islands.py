"""Tests for multi-island layout primitives."""

import tempfile
from pathlib import Path

import pytest

from coral.hub._island import island_root


def test_island_root_single_island_no_islands_dir():
    """When .coral/islands/ does not exist, island_root returns public/ regardless of id."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        # No islands/ dir created
        assert island_root(coral_dir, None) == coral_dir / "public"
        # Even with island_id, single-island layout returns public/
        assert island_root(coral_dir, "0") == coral_dir / "public"


def test_island_root_multi_island_with_id():
    """When islands/ exists, island_root returns the per-island subdir."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "islands").mkdir()
        assert island_root(coral_dir, "0") == coral_dir / "islands" / "0"
        assert island_root(coral_dir, "3") == coral_dir / "islands" / "3"
        # Integer ids are stringified
        assert island_root(coral_dir, 2) == coral_dir / "islands" / "2"


def test_island_root_multi_island_requires_id():
    """In multi-island layout, island_id=None is an error."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "islands").mkdir()
        with pytest.raises(ValueError, match="island_id is required"):
            island_root(coral_dir, None)


def test_island_root_rejects_invalid_ids():
    """Reject empty, separator-bearing, and traversal-bearing island_ids."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "islands").mkdir()
        for bad in ("", "..", "../escape", "0/notes", "a/b"):
            with pytest.raises(ValueError, match="invalid"):
                island_root(coral_dir, bad)


def test_island_root_accepts_integer_zero():
    """Integer 0 (often a valid first-island id) must round-trip cleanly."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "islands").mkdir()
        assert island_root(coral_dir, 0) == coral_dir / "islands" / "0"


from coral.hub.attempts import (
    get_leaderboard,
    increment_eval_count,
    read_attempts,
    read_eval_count,
    write_attempt,
)
from coral.types import Attempt


def _make_attempt(commit: str, agent: str = "agent-1", score: float = 0.5) -> Attempt:
    return Attempt(
        commit_hash=commit,
        agent_id=agent,
        title="t",
        score=score,
        status="improved",
        parent_hash=None,
        timestamp="2026-05-31T10:00:00Z",
    )


def _make_multi_island(coral_dir: Path, n: int = 2) -> None:
    """Create a multi-island layout with N empty islands."""
    for i in range(n):
        (coral_dir / "islands" / str(i) / "attempts").mkdir(parents=True)


def test_write_attempt_multi_island_writes_to_island_dir():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        _make_multi_island(coral_dir, n=2)
        write_attempt(coral_dir, _make_attempt("aaa"), island_id="0")
        write_attempt(coral_dir, _make_attempt("bbb"), island_id="1")
        assert (coral_dir / "islands" / "0" / "attempts" / "aaa.json").exists()
        assert (coral_dir / "islands" / "1" / "attempts" / "bbb.json").exists()
        # Cross-island isolation: island 0 does not see island 1's attempt
        assert not (coral_dir / "islands" / "0" / "attempts" / "bbb.json").exists()


def test_read_attempts_multi_island_isolation():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        _make_multi_island(coral_dir, n=2)
        write_attempt(coral_dir, _make_attempt("aaa", score=0.8), island_id="0")
        write_attempt(coral_dir, _make_attempt("bbb", score=0.6), island_id="1")
        island0 = read_attempts(coral_dir, island_id="0")
        island1 = read_attempts(coral_dir, island_id="1")
        assert {a.commit_hash for a in island0} == {"aaa"}
        assert {a.commit_hash for a in island1} == {"bbb"}


def test_read_attempts_single_island_default_island_id():
    """Pre-existing behavior: no island_id passed, reads from public/."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        write_attempt(coral_dir, _make_attempt("ccc"))
        # Single-island layout: islands/ does not exist on disk
        assert (coral_dir / "public" / "attempts" / "ccc.json").exists()
        assert {a.commit_hash for a in read_attempts(coral_dir)} == {"ccc"}


def test_eval_count_multi_island_global_and_per_island():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        _make_multi_island(coral_dir, n=2)
        increment_eval_count(coral_dir, island_id="0")
        increment_eval_count(coral_dir, island_id="0")
        increment_eval_count(coral_dir, island_id="1")
        # Per-island counters reflect their own evals
        assert read_eval_count(coral_dir, island_id="0") == 2
        assert read_eval_count(coral_dir, island_id="1") == 1
        # Global counter (island_id=None) was also bumped each time
        assert read_eval_count(coral_dir, island_id=None) == 3


from coral.hub.notes import list_notes, notes_by


def test_list_notes_multi_island_isolation():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        for i in range(2):
            (coral_dir / "islands" / str(i) / "notes").mkdir(parents=True)
        (coral_dir / "islands" / "0" / "notes" / "a.md").write_text(
            "---\ncreator: agent-1\ncreated: 2026-05-31\n---\n# A\nbody A\n"
        )
        (coral_dir / "islands" / "1" / "notes" / "b.md").write_text(
            "---\ncreator: agent-2\ncreated: 2026-05-31\n---\n# B\nbody B\n"
        )
        names0 = {e["filename"] for e in list_notes(coral_dir, island_id="0")}
        names1 = {e["filename"] for e in list_notes(coral_dir, island_id="1")}
        assert names0 == {"a.md"}
        assert names1 == {"b.md"}


def test_notes_by_returns_creator_matched_paths():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "islands" / "0" / "notes").mkdir(parents=True)
        notes = coral_dir / "islands" / "0" / "notes"
        (notes / "by-agent-1.md").write_text("---\ncreator: agent-1\n---\nbody\n")
        (notes / "by-agent-2.md").write_text("---\ncreator: agent-2\n---\nbody\n")
        (notes / "anonymous.md").write_text("# no frontmatter\nbody\n")
        matched = notes_by(coral_dir, island_id="0", agent_id="agent-1")
        assert [p.name for p in matched] == ["by-agent-1.md"]
        # The anonymous note (no creator) is excluded
        all_matched = (
            notes_by(coral_dir, island_id="0", agent_id="agent-1")
            + notes_by(coral_dir, island_id="0", agent_id="agent-2")
        )
        assert "anonymous.md" not in {p.name for p in all_matched}


def test_notes_by_single_island_uses_public():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        notes = coral_dir / "public" / "notes"
        notes.mkdir(parents=True)
        (notes / "n.md").write_text("---\ncreator: agent-1\n---\nbody\n")
        matched = notes_by(coral_dir, island_id=None, agent_id="agent-1")
        assert [p.name for p in matched] == ["n.md"]


def test_notes_by_matches_in_subdirectory():
    """notes_by walks subdirectories via rglob."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        sub = coral_dir / "islands" / "0" / "notes" / "research"
        sub.mkdir(parents=True)
        (sub / "deep.md").write_text("---\ncreator: agent-3\n---\nbody\n")
        matched = notes_by(coral_dir, island_id="0", agent_id="agent-3")
        assert [p.name for p in matched] == ["deep.md"]


def test_notes_by_skips_malformed_files():
    """notes_by tolerates unreadable / binary .md files."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        notes = coral_dir / "islands" / "0" / "notes"
        notes.mkdir(parents=True)
        (notes / "good.md").write_text("---\ncreator: agent-1\n---\nbody\n")
        # Invalid UTF-8 sequence; .md extension matches rglob but read_text will raise
        (notes / "bad.md").write_bytes(b"\xff\xfe\xfd\x00not utf-8\xff\xff")
        matched = notes_by(coral_dir, island_id="0", agent_id="agent-1")
        assert [p.name for p in matched] == ["good.md"]
