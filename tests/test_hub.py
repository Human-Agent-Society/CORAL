"""Tests for hub (attempts, notes, skills)."""

import tempfile
from pathlib import Path

from coral.hub.attempts import (
    format_leaderboard,
    get_agent_attempts,
    get_leaderboard,
    per_agent_class_counts,
    read_attempts,
    search_attempts,
    write_attempt,
)
from coral.hub.notes import (
    copy_notes_to_island,
    format_notes_list,
    get_recent_notes,
    list_notes,
    mark_notes_legacy,
    notes_by,
    read_note,
    search_notes,
)
from coral.hub.skills import get_skill_tree, list_skills, read_skill
from coral.types import Attempt


def _make_attempt(
    commit: str, agent: str = "agent-1", score: float = 0.5, title: str = "test"
) -> Attempt:
    return Attempt(
        commit_hash=commit,
        agent_id=agent,
        title=title,
        score=score,
        status="improved",
        parent_hash=None,
        timestamp="2026-03-11T10:00:00Z",
    )


def test_attempts_crud():
    with tempfile.TemporaryDirectory() as d:
        a1 = _make_attempt("aaa111", score=0.8, title="approach A")
        a2 = _make_attempt("bbb222", agent="agent-2", score=0.6, title="approach B")

        write_attempt(d, a1)
        write_attempt(d, a2)

        all_attempts = read_attempts(d)
        assert len(all_attempts) == 2


def test_leaderboard():
    with tempfile.TemporaryDirectory() as d:
        write_attempt(d, _make_attempt("a", score=0.3))
        write_attempt(d, _make_attempt("b", score=0.9))
        write_attempt(d, _make_attempt("c", score=0.6))

        top = get_leaderboard(d, top_n=2)
        assert len(top) == 2
        assert top[0].score == 0.9
        assert top[1].score == 0.6


def test_agent_filter():
    with tempfile.TemporaryDirectory() as d:
        write_attempt(d, _make_attempt("a", agent="agent-1"))
        write_attempt(d, _make_attempt("b", agent="agent-2"))
        write_attempt(d, _make_attempt("c", agent="agent-1"))

        agent1 = get_agent_attempts(d, "agent-1")
        assert len(agent1) == 2


def test_agent_filter_scans_migrated_agent_current_island():
    """A prefixed agent id is birth lineage, not current island after migration."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        for island in ("0", "1"):
            (coral_dir / "islands" / island / "attempts").mkdir(parents=True)

        write_attempt(coral_dir, _make_attempt("after-move", agent="0-agent-1"), island_id="1")

        assert get_agent_attempts(coral_dir, "0-agent-1", island_id="0") == []
        assert len(get_agent_attempts(coral_dir, "0-agent-1", island_id="1")) == 1
        assert len(get_agent_attempts(coral_dir, "0-agent-1")) == 1


def test_search():
    with tempfile.TemporaryDirectory() as d:
        write_attempt(d, _make_attempt("a", title="learning rate tuning"))
        write_attempt(d, _make_attempt("b", title="attention heads"))
        write_attempt(d, _make_attempt("c", title="learning rate schedule"))

        results = search_attempts(d, "learning rate")
        assert len(results) == 2


def test_format_leaderboard():
    attempts = [_make_attempt("a", score=0.9), _make_attempt("b", score=0.5)]
    md = format_leaderboard(attempts)
    assert "Rank" in md
    assert "0.9000" in md


def test_format_leaderboard_shows_class_column():
    """The Class column distinguishes real / tune / error attempts at a glance."""
    real = _make_attempt("aaa", score=0.9, title="real-row")
    tune = _make_attempt("bbb", score=0.5, title="tune-row")
    tune.metadata["budget_class"] = "tune"
    err = _make_attempt("ccc", score=0.3, title="error-row")
    err.metadata["budget_class"] = "grader_error"

    md = format_leaderboard([real, tune, err])
    assert "Class" in md
    # Per-row class labels appear in the table body.
    real_line = next(line for line in md.splitlines() if "real-row" in line)
    tune_line = next(line for line in md.splitlines() if "tune-row" in line)
    err_line = next(line for line in md.splitlines() if "error-row" in line)
    assert " real " in real_line
    assert " tune " in tune_line
    # grader_error is rendered as compact "error" to keep the column narrow.
    assert " error " in err_line
    assert "grader_error" not in err_line


def test_per_agent_class_counts_splits_by_budget_class():
    """Budget class counts are tallied per agent (issue #73)."""
    with tempfile.TemporaryDirectory() as d:
        # agent-1: 2 real, 1 grader_error, 1 tune
        a = _make_attempt("aaa", agent="agent-1")
        b = _make_attempt("bbb", agent="agent-1")
        c = _make_attempt("ccc", agent="agent-1")
        c.metadata["budget_class"] = "grader_error"
        c.status = "timeout"
        d_att = _make_attempt("ddd", agent="agent-1")
        d_att.metadata["budget_class"] = "tune"

        # agent-2: 1 real
        e = _make_attempt("eee", agent="agent-2")

        for att in (a, b, c, d_att, e):
            write_attempt(d, att)

        counts = per_agent_class_counts(d)
        assert counts["agent-1"] == {"real": 2, "grader_error": 1, "tune": 1}
        assert counts["agent-2"] == {"real": 1}


def test_per_agent_class_counts_skips_pending():
    """Pending attempts have no final classification — exclude from tallies."""
    with tempfile.TemporaryDirectory() as d:
        scored = _make_attempt("aaa", agent="agent-1")
        pending = _make_attempt("bbb", agent="agent-1")
        pending.status = "pending"
        pending.score = None

        write_attempt(d, scored)
        write_attempt(d, pending)

        counts = per_agent_class_counts(d)
        assert counts["agent-1"] == {"real": 1}


def test_notes():
    with tempfile.TemporaryDirectory() as d:
        # Write notes in public/notes/notes.md
        (Path(d) / "public" / "notes").mkdir(parents=True)
        notes_file = Path(d) / "public" / "notes" / "notes.md"
        notes_file.write_text(
            "## [2026-03-11] ReLU works better\n"
            "Details about ReLU activation...\n"
            "\n"
            "## [2026-03-11] Learning rate 0.001 is optimal\n"
            "Tried various learning rates...\n"
        )

        entries = list_notes(d)
        assert len(entries) == 2
        assert entries[0]["title"] == "ReLU works better"
        assert entries[1]["title"] == "Learning rate 0.001 is optimal"

        # Read specific entry
        content = read_note(d, 1)
        assert content is not None
        assert "ReLU" in content
        assert "Details" in content

        # Search
        results = search_notes(d, "learning rate")
        assert len(results) == 1
        assert results[0]["title"] == "Learning rate 0.001 is optimal"

        # Recent
        recent = get_recent_notes(d, n=1)
        assert len(recent) == 1
        assert recent[0]["title"] == "Learning rate 0.001 is optimal"

        # Format
        formatted = format_notes_list(entries)
        assert "ReLU" in formatted
        assert "Learning rate" in formatted


def test_notes_empty():
    with tempfile.TemporaryDirectory() as d:
        entries = list_notes(d)
        assert entries == []
        assert format_notes_list(entries) == "No notes yet."


def _write_note(notes_dir: Path, name: str, body: str) -> Path:
    notes_dir.mkdir(parents=True, exist_ok=True)
    path = notes_dir / name
    path.write_text(body)
    return path


def test_mark_notes_legacy_stamps_and_moves_authored_notes():
    """Notes by the agent get `legacy: true` and move under `_legacy/`; others untouched."""
    with tempfile.TemporaryDirectory() as d:
        notes_dir = Path(d) / "public" / "notes"
        mine = _write_note(
            notes_dir,
            "tiling.md",
            "---\ncreator: agent-1\ncreated: 2026-03-14\nclaim: tiling helps\n---\n\n# Tiling\nbody\n",
        )
        theirs = _write_note(
            notes_dir,
            "other.md",
            "---\ncreator: agent-2\ncreated: 2026-03-14\n---\n\n# Other\nbody\n",
        )

        marked = mark_notes_legacy(d, island_id=None, agent_id="agent-1", reason="migrated to 1")

        moved = notes_dir / "_legacy" / "tiling.md"
        assert marked == [moved]
        # The original is gone; the note now lives under _legacy/.
        assert not mine.exists()
        assert moved.exists()
        moved_text = moved.read_text()
        assert "legacy: true" in moved_text
        assert 'legacy_reason: "migrated to 1"' in moved_text
        # Existing frontmatter + body survive the surgical insert.
        assert "creator: agent-1" in moved_text
        assert "claim: tiling helps" in moved_text
        assert "# Tiling" in moved_text
        # Another agent's note is left alone, in place.
        assert theirs.exists()
        assert "legacy" not in theirs.read_text()


def test_mark_notes_legacy_preserves_subdir_structure():
    """A categorized note keeps its relative path under `_legacy/`."""
    with tempfile.TemporaryDirectory() as d:
        notes_dir = Path(d) / "public" / "notes"
        nested = _write_note(
            notes_dir / "research",
            "idea.md",
            "---\ncreator: agent-1\ncreated: 2026-03-14\n---\n\n# Idea\nbody\n",
        )

        marked = mark_notes_legacy(d, island_id=None, agent_id="agent-1")

        moved = notes_dir / "_legacy" / "research" / "idea.md"
        assert marked == [moved]
        assert not nested.exists()
        assert moved.exists()


def test_mark_notes_legacy_is_idempotent():
    """A second call doesn't re-stamp, re-move, or duplicate the legacy field."""
    with tempfile.TemporaryDirectory() as d:
        notes_dir = Path(d) / "public" / "notes"
        _write_note(
            notes_dir,
            "n.md",
            "---\ncreator: agent-1\ncreated: 2026-03-14\n---\n\n# N\nbody\n",
        )

        moved = notes_dir / "_legacy" / "n.md"
        first = mark_notes_legacy(d, island_id=None, agent_id="agent-1")
        assert first == [moved]
        second = mark_notes_legacy(d, island_id=None, agent_id="agent-1")
        assert second == []
        # The note stays parked under _legacy/ with a single legacy stamp.
        assert moved.read_text().count("legacy: true") == 1


def test_mark_notes_legacy_skips_unattributed():
    """A note with no creator can't be attributed, so it's never flagged or moved."""
    with tempfile.TemporaryDirectory() as d:
        notes_dir = Path(d) / "public" / "notes"
        anon = _write_note(notes_dir, "anon.md", "# Anon\nno frontmatter\n")

        marked = mark_notes_legacy(d, island_id=None, agent_id="agent-1")

        assert marked == []
        assert anon.exists()
        assert "legacy" not in anon.read_text()
        assert not (notes_dir / "_legacy").exists()


def test_mark_notes_legacy_surfaces_in_list_and_format():
    """The legacy flag round-trips through list_notes and format_notes_list."""
    with tempfile.TemporaryDirectory() as d:
        notes_dir = Path(d) / "public" / "notes"
        _write_note(
            notes_dir,
            "n.md",
            "---\ncreator: agent-1\ncreated: 2026-03-14\n---\n\n# Legacy Note\nbody\n",
        )
        mark_notes_legacy(d, island_id=None, agent_id="agent-1")

        entries = list_notes(d)
        assert len(entries) == 1
        assert entries[0]["legacy"] is True
        assert "[legacy]" in format_notes_list(entries)
        # The note moved under _legacy/ but is still attributable to its author.
        assert notes_by(d, island_id=None, agent_id="agent-1") == [notes_dir / "_legacy" / "n.md"]


def test_copy_notes_to_island_carries_authored_notes():
    """An agent's live notes are copied to the destination island, attributed and live."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        src = coral_dir / "islands" / "0" / "notes"
        dst = coral_dir / "islands" / "1" / "notes"
        dst.mkdir(parents=True)
        _write_note(
            src,
            "tiling.md",
            "---\ncreator: 0-agent-1\ncreated: 2026-03-14\nclaim: tiling helps\n---\n\n# Tiling\nbody\n",
        )
        _write_note(
            src / "research",
            "idea.md",
            "---\ncreator: 0-agent-1\ncreated: 2026-03-14\n---\n\n# Idea\nbody\n",
        )
        _write_note(
            src,
            "teammate.md",
            "---\ncreator: 0-agent-2\ncreated: 2026-03-14\n---\n\n# Teammate\nbody\n",
        )

        copied = copy_notes_to_island(coral_dir, "0-agent-1", src_island="0", dst_island="1")

        assert sorted(copied) == [dst / "research" / "idea.md", dst / "tiling.md"]
        # Relative structure preserved; copies stay attributed and are NOT legacy.
        copy_text = (dst / "tiling.md").read_text()
        assert "creator: 0-agent-1" in copy_text
        assert "claim: tiling helps" in copy_text
        assert "legacy" not in copy_text
        assert notes_by(coral_dir, island_id="1", agent_id="0-agent-1") == [
            dst / "research" / "idea.md",
            dst / "tiling.md",
        ]
        # Teammate's note didn't ride along.
        assert not (dst / "teammate.md").exists()
        # Source island is left untouched by the copy.
        assert (src / "tiling.md").exists()


def test_copy_notes_to_island_skips_already_legacy_and_avoids_collisions():
    """Already-archived notes aren't re-carried; same-named dst notes aren't clobbered."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        src = coral_dir / "islands" / "0" / "notes"
        dst = coral_dir / "islands" / "1" / "notes"
        dst.mkdir(parents=True)
        # A live note that should be carried...
        _write_note(
            src,
            "live.md",
            "---\ncreator: 0-agent-1\ncreated: 2026-03-14\n---\n\n# Live\nbody\n",
        )
        # ...and one already archived as legacy on the source (under _legacy/).
        _write_note(
            src / "_legacy",
            "old.md",
            "---\ncreator: 0-agent-1\ncreated: 2026-03-14\nlegacy: true\n---\n\n# Old\nbody\n",
        )
        # The destination already has a same-named note by someone else.
        _write_note(
            dst,
            "live.md",
            "---\ncreator: 1-agent-9\ncreated: 2026-03-14\n---\n\n# Pre-existing\nkeep me\n",
        )

        copied = copy_notes_to_island(coral_dir, "0-agent-1", src_island="0", dst_island="1")

        # legacy note skipped; live note copied under a non-clobbering name.
        assert copied == [dst / "live-2.md"]
        assert "keep me" in (dst / "live.md").read_text()
        assert not (dst / "old.md").exists()
        assert not (dst / "_legacy" / "old.md").exists()


def test_skills():
    with tempfile.TemporaryDirectory() as d:
        skill_dir = Path(d) / "public" / "skills" / "my_tool"
        skill_dir.mkdir(parents=True)
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()

        (skill_dir / "SKILL.md").write_text(
            "---\nname: my_tool\ndescription: A useful tool\ncreator: agent-1\n---\n# My Tool\nUsage..."
        )
        (scripts_dir / "run.py").write_text("print('hello')")

        skills = list_skills(d)
        assert len(skills) == 1
        assert skills[0]["name"] == "my_tool"

        info = read_skill(str(skill_dir))
        assert "run.py" in str(info["files"])
        assert "Usage" in info["body"]

        tree = get_skill_tree(str(skill_dir))
        assert "SKILL.md" in tree
