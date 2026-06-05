"""Tests for multi-island layout primitives."""

import tempfile
from pathlib import Path

import pytest

from coral.hub._island import island_root
from coral.hub.attempts import (
    increment_eval_count,
    read_attempts,
    read_eval_count,
    write_attempt,
)
from coral.hub.checkpoint import (
    checkpoint,
    checkpoint_history,
    init_checkpoint_repo,
)
from coral.hub.heartbeat import (
    read_agent_heartbeat,
    read_global_heartbeat,
    write_agent_heartbeat,
    write_global_heartbeat,
)
from coral.hub.notes import get_recent_notes, list_notes, notes_by
from coral.hub.skills import list_skills, skills_by
from coral.types import Attempt


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


def test_recent_notes_multi_island_uses_global_date_order():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        for i in range(2):
            (coral_dir / "islands" / str(i) / "notes").mkdir(parents=True)
        (coral_dir / "islands" / "0" / "notes" / "old.md").write_text(
            "---\ncreator: agent-1\ncreated: 2026-06-01T00:00:00Z\n---\n# Old\nbody\n"
        )
        (coral_dir / "islands" / "0" / "notes" / "new.md").write_text(
            "---\ncreator: agent-1\ncreated: 2026-06-03T00:00:00Z\n---\n# New\nbody\n"
        )
        (coral_dir / "islands" / "1" / "notes" / "middle.md").write_text(
            "---\ncreator: agent-2\ncreated: 2026-06-02T00:00:00Z\n---\n# Middle\nbody\n"
        )

        recent = get_recent_notes(coral_dir, n=2)

        assert [entry["title"] for entry in recent] == ["Middle", "New"]
        assert [entry["island_id"] for entry in recent] == ["1", "0"]


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
        all_matched = notes_by(coral_dir, island_id="0", agent_id="agent-1") + notes_by(
            coral_dir, island_id="0", agent_id="agent-2"
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


def _write_skill(dir_: Path, name: str, creator: str | None) -> None:
    """Helper: create a skill dir with SKILL.md, optionally stamped with `creator:`."""
    sk_dir = dir_ / name
    sk_dir.mkdir(parents=True)
    if creator is None:
        sk_dir.joinpath("SKILL.md").write_text(
            f"---\nname: {name}\ndescription: test skill\n---\nbody\n"
        )
    else:
        sk_dir.joinpath("SKILL.md").write_text(
            f"---\nname: {name}\ndescription: test skill\ncreator: {creator}\n---\nbody\n"
        )


def test_list_skills_multi_island_isolation():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        for i in range(2):
            (coral_dir / "islands" / str(i) / "skills").mkdir(parents=True)
        _write_skill(coral_dir / "islands" / "0" / "skills", "alpha", creator="agent-1")
        _write_skill(coral_dir / "islands" / "1" / "skills", "beta", creator="agent-2")
        names0 = {s["name"] for s in list_skills(coral_dir, island_id="0")}
        names1 = {s["name"] for s in list_skills(coral_dir, island_id="1")}
        assert names0 == {"alpha"}
        assert names1 == {"beta"}


def test_skills_by_excludes_bundled_unstamped_skills():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        skills_dir = coral_dir / "islands" / "0" / "skills"
        skills_dir.mkdir(parents=True)
        _write_skill(skills_dir, "agent-built", creator="agent-1")
        _write_skill(skills_dir, "bundled", creator=None)
        matched = skills_by(coral_dir, island_id="0", agent_id="agent-1")
        assert [p.name for p in matched] == ["agent-built"]


def test_skills_by_single_island_uses_public():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        skills_dir = coral_dir / "public" / "skills"
        skills_dir.mkdir(parents=True)
        _write_skill(skills_dir, "mine", creator="agent-7")
        matched = skills_by(coral_dir, island_id=None, agent_id="agent-7")
        assert [p.name for p in matched] == ["mine"]


def test_heartbeat_multi_island_isolation():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        for i in range(2):
            (coral_dir / "islands" / str(i) / "heartbeat").mkdir(parents=True)
        write_agent_heartbeat(
            coral_dir,
            "agent-1",
            [{"name": "reflect", "every": 1, "prompt": "island-0 reflect"}],
            island_id="0",
        )
        write_agent_heartbeat(
            coral_dir,
            "agent-1",
            [{"name": "reflect", "every": 2, "prompt": "island-1 reflect"}],
            island_id="1",
        )
        a0 = read_agent_heartbeat(coral_dir, "agent-1", island_id="0")
        a1 = read_agent_heartbeat(coral_dir, "agent-1", island_id="1")
        assert next(a for a in a0 if a["name"] == "reflect")["every"] == 1
        assert next(a for a in a1 if a["name"] == "reflect")["every"] == 2


def test_global_heartbeat_multi_island_isolation():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        for i in range(2):
            (coral_dir / "islands" / str(i) / "heartbeat").mkdir(parents=True)
        write_global_heartbeat(coral_dir, [{"name": "consolidate", "every": 10}], island_id="0")
        write_global_heartbeat(coral_dir, [{"name": "consolidate", "every": 20}], island_id="1")
        g0 = read_global_heartbeat(coral_dir, island_id="0")
        g1 = read_global_heartbeat(coral_dir, island_id="1")
        assert next(a for a in g0 if a["name"] == "consolidate")["every"] == 10
        assert next(a for a in g1 if a["name"] == "consolidate")["every"] == 20


def test_heartbeat_multi_island_unscoped_writes_are_rejected():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "islands" / "0" / "heartbeat").mkdir(parents=True)

        with pytest.raises(ValueError, match="island_id is required"):
            write_agent_heartbeat(coral_dir, "agent-1", [])
        with pytest.raises(ValueError, match="island_id is required"):
            write_global_heartbeat(coral_dir, [])


def test_checkpoint_multi_island_separate_repos():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        for i in range(2):
            (coral_dir / "islands" / str(i) / "notes").mkdir(parents=True)
        init_checkpoint_repo(str(coral_dir), island_id="0")
        init_checkpoint_repo(str(coral_dir), island_id="1")

        # Distinct .git dirs per island
        assert (coral_dir / "islands" / "0" / ".git").is_dir()
        assert (coral_dir / "islands" / "1" / ".git").is_dir()

        # Write a note on island 0, checkpoint it
        (coral_dir / "islands" / "0" / "notes" / "a.md").write_text("hello island 0")
        h0 = checkpoint(str(coral_dir), "agent-1", "note on island 0", island_id="0")
        assert h0 is not None

        # Island 1 does not see island 0's commit
        h1_history = checkpoint_history(str(coral_dir), island_id="1")
        assert all("island 0" not in entry["message"] for entry in h1_history)


def test_checkpoint_single_island_default_unchanged():
    """Regression: existing single-island callers (no island_id) still use public/.git."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "public" / "notes").mkdir(parents=True)
        init_checkpoint_repo(str(coral_dir))
        assert (coral_dir / "public" / ".git").is_dir()
        (coral_dir / "public" / "notes" / "a.md").write_text("hello")
        h = checkpoint(str(coral_dir), "agent-1", "first note")
        assert h is not None
