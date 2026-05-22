"""Tests for coral.hub.falsifications — quorum + TTL aggregation over notes."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from coral.hub.falsifications import (
    Claim,
    TopicStatus,
    find_consensus,
    find_disputed,
    list_topics,
    topic_status,
    validate_slug,
)


def _write_note(
    notes_dir: Path,
    *,
    filename: str,
    creator: str,
    falsifies: str,
    claimed_at_eval: int,
    ttl_evals: int | None = None,
    body: str = "Reasoning goes here.",
) -> Path:
    """Write a note file with the given falsification frontmatter."""
    notes_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f"creator: {creator}",
        "created: 2026-05-16T10:00:00+00:00",
        f"falsifies: {falsifies}",
        f"claimed_at_eval: {claimed_at_eval}",
    ]
    if ttl_evals is not None:
        lines.append(f"ttl_evals: {ttl_evals}")
    lines.extend(["---", "", "# Why this is dead", "", body, ""])
    p = notes_dir / filename
    p.write_text("\n".join(lines))
    return p


def _setup_coral_dir(tmpdir: str) -> Path:
    """Build the minimal .coral/ skeleton expected by hub modules."""
    coral_dir = Path(tmpdir) / ".coral"
    (coral_dir / "public" / "notes").mkdir(parents=True)
    return coral_dir


def test_validate_slug_accepts_kebab_case():
    validate_slug("xfmr-distill")
    validate_slug("a")
    validate_slug("a1-b2-c3")
    validate_slug("ssm-distill-student")
    validate_slug("v3")


def test_validate_slug_rejects_non_kebab_case():
    bad = [
        "",
        "XfmrDistill",
        "xfmr_distill",
        "xfmr distill",
        "-leading",
        "trailing-",
        "double--dash",
        "Capital",
        "snake_case_topic",
        "with.dot",
        "with/slash",
    ]
    for s in bad:
        with pytest.raises(ValueError):
            validate_slug(s)


def test_single_voice_within_ttl_is_disputed():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = _setup_coral_dir(d)
        notes_dir = coral_dir / "public" / "notes"
        _write_note(
            notes_dir,
            filename="agent-1-claim.md",
            creator="agent-1",
            falsifies="xfmr-distill",
            claimed_at_eval=10,
        )
        topics = list_topics(coral_dir, current_eval=15, quorum=2, default_ttl=30)
        assert len(topics) == 1
        s = topics[0]
        assert s.topic == "xfmr-distill"
        assert s.level == "disputed"
        assert s.voices == ["agent-1"]


def test_two_distinct_voices_within_ttl_is_consensus():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = _setup_coral_dir(d)
        notes_dir = coral_dir / "public" / "notes"
        _write_note(
            notes_dir,
            filename="agent-1-claim.md",
            creator="agent-1",
            falsifies="xfmr-distill",
            claimed_at_eval=10,
        )
        _write_note(
            notes_dir,
            filename="agent-2-claim.md",
            creator="agent-2",
            falsifies="xfmr-distill",
            claimed_at_eval=12,
        )
        topics = list_topics(coral_dir, current_eval=15, quorum=2, default_ttl=30)
        assert len(topics) == 1
        s = topics[0]
        assert s.level == "consensus"
        assert s.voices == ["agent-1", "agent-2"]
        # Latest expiry across active claims
        assert s.expires_at_eval == 42


def test_two_voices_both_expired_is_stale():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = _setup_coral_dir(d)
        notes_dir = coral_dir / "public" / "notes"
        _write_note(
            notes_dir,
            filename="agent-1-claim.md",
            creator="agent-1",
            falsifies="xfmr-distill",
            claimed_at_eval=10,
            ttl_evals=5,
        )
        _write_note(
            notes_dir,
            filename="agent-2-claim.md",
            creator="agent-2",
            falsifies="xfmr-distill",
            claimed_at_eval=12,
            ttl_evals=5,
        )
        topics = list_topics(coral_dir, current_eval=100, quorum=2, default_ttl=30)
        assert len(topics) == 1
        s = topics[0]
        assert s.level == "stale"
        assert s.voices == []  # no ACTIVE voices
        assert s.all_voices == ["agent-1", "agent-2"]


def test_same_agent_two_claims_does_not_reach_quorum():
    """Two claims from the same agent should not satisfy quorum=2 — quorum
    counts DISTINCT agents."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = _setup_coral_dir(d)
        notes_dir = coral_dir / "public" / "notes"
        _write_note(
            notes_dir,
            filename="claim-1.md",
            creator="agent-1",
            falsifies="xfmr-distill",
            claimed_at_eval=10,
        )
        _write_note(
            notes_dir,
            filename="claim-2.md",
            creator="agent-1",
            falsifies="xfmr-distill",
            claimed_at_eval=12,
        )
        topics = list_topics(coral_dir, current_eval=15, quorum=2, default_ttl=30)
        assert topics[0].level == "disputed"
        assert topics[0].voices == ["agent-1"]


def test_quorum_one_promotes_single_voice_to_consensus():
    """For single-agent runs, quorum=1 means a lone claim is consensus."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = _setup_coral_dir(d)
        notes_dir = coral_dir / "public" / "notes"
        _write_note(
            notes_dir,
            filename="claim.md",
            creator="agent-1",
            falsifies="xfmr-distill",
            claimed_at_eval=10,
        )
        topics = list_topics(coral_dir, current_eval=15, quorum=1, default_ttl=30)
        assert topics[0].level == "consensus"


def test_one_active_one_expired_still_disputed():
    """If one voice has expired, it stops counting toward quorum."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = _setup_coral_dir(d)
        notes_dir = coral_dir / "public" / "notes"
        _write_note(
            notes_dir,
            filename="old.md",
            creator="agent-1",
            falsifies="xfmr-distill",
            claimed_at_eval=10,
            ttl_evals=5,  # expires at eval 15
        )
        _write_note(
            notes_dir,
            filename="fresh.md",
            creator="agent-2",
            falsifies="xfmr-distill",
            claimed_at_eval=50,
            ttl_evals=30,  # expires at eval 80
        )
        topics = list_topics(coral_dir, current_eval=60, quorum=2, default_ttl=30)
        s = topics[0]
        assert s.level == "disputed"
        assert s.voices == ["agent-2"]  # agent-1's claim expired
        assert s.all_voices == ["agent-1", "agent-2"]


def test_unrelated_topics_are_independent():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = _setup_coral_dir(d)
        notes_dir = coral_dir / "public" / "notes"
        _write_note(
            notes_dir,
            filename="a.md",
            creator="agent-1",
            falsifies="xfmr-distill",
            claimed_at_eval=10,
        )
        _write_note(
            notes_dir,
            filename="b.md",
            creator="agent-2",
            falsifies="ssm-distill",
            claimed_at_eval=11,
        )
        topics = list_topics(coral_dir, current_eval=15, quorum=2, default_ttl=30)
        assert len(topics) == 2
        # Each topic has only one voice → both disputed
        assert all(t.level == "disputed" for t in topics)
        assert sorted(t.topic for t in topics) == ["ssm-distill", "xfmr-distill"]


def test_notes_without_falsifies_field_are_ignored():
    """Plain research/synthesis notes shouldn't be treated as claims."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = _setup_coral_dir(d)
        notes_dir = coral_dir / "public" / "notes"
        # plain note (no falsifies field)
        plain = notes_dir / "plain.md"
        plain.write_text(
            "---\ncreator: agent-1\ncreated: 2026-05-16\n---\n# Just thoughts\n"
        )
        # claim note
        _write_note(
            notes_dir,
            filename="claim.md",
            creator="agent-1",
            falsifies="xfmr-distill",
            claimed_at_eval=10,
        )
        topics = list_topics(coral_dir, current_eval=15, quorum=2, default_ttl=30)
        assert len(topics) == 1
        assert topics[0].topic == "xfmr-distill"


def test_note_with_invalid_slug_is_skipped():
    """If an agent hand-edits frontmatter with a bad slug, skip silently."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = _setup_coral_dir(d)
        notes_dir = coral_dir / "public" / "notes"
        bad = notes_dir / "bad.md"
        bad.write_text(
            "---\n"
            "creator: agent-1\n"
            "created: 2026-05-16\n"
            "falsifies: BadSlug_with_underscore\n"
            "claimed_at_eval: 10\n"
            "---\n# bad\n"
        )
        _write_note(
            notes_dir,
            filename="good.md",
            creator="agent-1",
            falsifies="good-slug",
            claimed_at_eval=10,
        )
        topics = list_topics(coral_dir, current_eval=15, quorum=2, default_ttl=30)
        assert len(topics) == 1
        assert topics[0].topic == "good-slug"


def test_default_ttl_used_when_unset_in_note():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = _setup_coral_dir(d)
        notes_dir = coral_dir / "public" / "notes"
        _write_note(
            notes_dir,
            filename="claim.md",
            creator="agent-1",
            falsifies="xfmr-distill",
            claimed_at_eval=10,
            ttl_evals=None,  # not written
        )
        # default_ttl=30 means active until eval 40
        active_topics = list_topics(coral_dir, current_eval=39, quorum=2, default_ttl=30)
        assert active_topics[0].level == "disputed"
        stale_topics = list_topics(coral_dir, current_eval=41, quorum=2, default_ttl=30)
        assert stale_topics[0].level == "stale"


def test_find_disputed_excludes_consensus():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = _setup_coral_dir(d)
        notes_dir = coral_dir / "public" / "notes"
        # Consensus: 2 voices on cnn-distill
        _write_note(
            notes_dir,
            filename="cnn-1.md",
            creator="agent-1",
            falsifies="cnn-distill",
            claimed_at_eval=10,
        )
        _write_note(
            notes_dir,
            filename="cnn-2.md",
            creator="agent-2",
            falsifies="cnn-distill",
            claimed_at_eval=11,
        )
        # Disputed: 1 voice on xfmr-distill
        _write_note(
            notes_dir,
            filename="xfmr-1.md",
            creator="agent-1",
            falsifies="xfmr-distill",
            claimed_at_eval=10,
        )
        # Stale: claim past TTL
        _write_note(
            notes_dir,
            filename="ssm-1.md",
            creator="agent-1",
            falsifies="ssm-distill",
            claimed_at_eval=10,
            ttl_evals=5,
        )

        disputed = find_disputed(coral_dir, current_eval=20, quorum=2, default_ttl=30)
        topics_returned = sorted(s.topic for s in disputed)
        assert topics_returned == ["ssm-distill", "xfmr-distill"]

        consensus = find_consensus(coral_dir, current_eval=20, quorum=2, default_ttl=30)
        assert [s.topic for s in consensus] == ["cnn-distill"]


def test_topic_status_for_unknown_topic():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = _setup_coral_dir(d)
        s = topic_status(
            "never-claimed",
            coral_dir,
            current_eval=10,
            quorum=2,
            default_ttl=30,
        )
        assert s.level == "unknown"


def test_topic_status_validates_slug():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = _setup_coral_dir(d)
        with pytest.raises(ValueError):
            topic_status("BadSlug", coral_dir, current_eval=0)


def test_dataclass_helpers():
    c = Claim(
        topic="x",
        creator="agent-1",
        claimed_at_eval=10,
        ttl_evals=20,
        note_path="claim.md",
        title="t",
    )
    assert c.expires_at_eval() == 30
    assert c.is_active(20) is True
    assert c.is_active(30) is False  # boundary: expired exactly at expires_at_eval
    assert c.is_active(31) is False

    s = TopicStatus(topic="x", level="disputed", voices=["agent-1"])
    assert s.evidence_paths() == []
