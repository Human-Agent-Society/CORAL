"""Aggregate falsification claims from note frontmatter into team consensus.

A note declares a topic falsified by adding two YAML frontmatter fields::

    ---
    creator: agent-1
    created: 2026-05-16T10:00:00+08:00
    falsifies: xfmr-distill-student   # kebab-case slug
    claimed_at_eval: 28               # global eval count when the claim was made
    # ttl_evals: 30                   # optional override
    ---

Multiple agents can independently claim the same topic (one note per claim).
This module groups them by topic, applies the configured TTL window, and
returns one of:

- ``consensus``  — at least ``quorum`` distinct agents have claimed the topic
                   AND at least one of those claims is still within TTL
- ``disputed``   — fewer than ``quorum`` distinct active claims, but at least
                   one is still within TTL
- ``stale``      — claims exist but ALL are past TTL
- ``unknown``    — no claim has ever been written (callers should not see)

The source of truth is the notes themselves — this module is read-only over
``list_notes()``.  No new on-disk format.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from coral.hub.notes import list_notes

StatusLevel = Literal["consensus", "disputed", "stale", "unknown"]

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def validate_slug(slug: str) -> None:
    """Raise ValueError unless ``slug`` is kebab-case (``[a-z0-9-]``).

    Examples that PASS: ``xfmr-distill``, ``ssm-distill-student``, ``cnn-2layer``
    Examples that FAIL: ``XfmrDistill``, ``xfmr_distill``, ``-leading-dash``,
    ``trailing-dash-``, ``double--dash``, empty string.
    """
    if not slug:
        raise ValueError("falsification slug cannot be empty")
    if not _SLUG_RE.fullmatch(slug):
        raise ValueError(
            f"falsification slug {slug!r} must be kebab-case "
            f"(lowercase letters/digits separated by single dashes), "
            f"e.g. 'xfmr-distill-student'"
        )


@dataclass
class Claim:
    """One agent's falsification claim, sourced from a single note."""

    topic: str
    creator: str
    claimed_at_eval: int
    ttl_evals: int
    note_path: str  # path relative to .coral/public/notes/, for citing
    title: str

    def expires_at_eval(self) -> int:
        return self.claimed_at_eval + self.ttl_evals

    def is_active(self, current_eval: int) -> bool:
        return current_eval < self.expires_at_eval()


@dataclass
class TopicStatus:
    """Aggregated status for a single falsification topic."""

    topic: str
    level: StatusLevel
    voices: list[str] = field(default_factory=list)  # distinct agent ids, active
    all_voices: list[str] = field(default_factory=list)  # distinct agent ids, including expired
    claims: list[Claim] = field(default_factory=list)  # sorted by claimed_at_eval ASC
    expires_at_eval: int = 0  # max expiry across active claims; 0 if none active

    def evidence_paths(self) -> list[str]:
        return [c.note_path for c in self.claims]


def _parse_int(value: Any, default: int = 0) -> int:
    """Robustly coerce a frontmatter scalar to int (notes use a hand-rolled parser
    that always returns strings)."""
    if value is None or value == "":
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _collect_claims(coral_dir: str | Path, default_ttl: int) -> list[Claim]:
    """Walk all notes via list_notes() and extract falsification claims.

    Notes without a ``falsifies`` field are skipped.  Notes whose slug fails
    validation are skipped (silent — the writer should already have been told
    via the CLI's `coral falsify` command).  Missing ``claimed_at_eval`` is
    treated as 0 so the claim ages out immediately (which surfaces a write-time
    bug rather than silently weighting the claim as fresh).
    """
    claims: list[Claim] = []
    for note in list_notes(coral_dir):
        topic = (note.get("falsifies") or "").strip()
        if not topic:
            continue
        try:
            validate_slug(topic)
        except ValueError:
            # Bad slug — skip silently. The CLI rejects writes; a bad slug here
            # means the agent edited frontmatter by hand. Surfacing it via
            # `coral disputed` would be noise.
            continue

        creator = (note.get("creator") or "").strip()
        if not creator:
            # Without a creator we can't count voices. Skip.
            continue

        claimed_at = _parse_int(note.get("claimed_at_eval"), default=0)
        ttl = _parse_int(note.get("ttl_evals"), default=default_ttl)
        if ttl <= 0:
            ttl = default_ttl

        # _path is set by list_notes() for individual files; legacy aggregated
        # notes don't have it (and they predate falsifications anyway).
        path_obj = note.get("_path")
        notes_root = Path(coral_dir) / "public" / "notes"
        try:
            rel_path = (
                str(Path(path_obj).resolve().relative_to(notes_root.resolve()))
                if path_obj
                else note.get("filename", "")
            )
        except ValueError:
            rel_path = note.get("filename", "")

        claims.append(
            Claim(
                topic=topic,
                creator=creator,
                claimed_at_eval=claimed_at,
                ttl_evals=ttl,
                note_path=rel_path,
                title=note.get("title", ""),
            )
        )
    return claims


def _classify(claims: list[Claim], current_eval: int, quorum: int) -> TopicStatus:
    """Compute a TopicStatus from a list of claims for the SAME topic."""
    assert claims, "_classify requires at least one claim"
    topic = claims[0].topic
    claims_sorted = sorted(claims, key=lambda c: c.claimed_at_eval)
    active = [c for c in claims_sorted if c.is_active(current_eval)]
    voices_active = sorted({c.creator for c in active})
    voices_all = sorted({c.creator for c in claims_sorted})
    expires_at = max((c.expires_at_eval() for c in active), default=0)

    if len(voices_active) >= quorum:
        level: StatusLevel = "consensus"
    elif active:
        level = "disputed"
    else:
        level = "stale"

    return TopicStatus(
        topic=topic,
        level=level,
        voices=voices_active,
        all_voices=voices_all,
        claims=claims_sorted,
        expires_at_eval=expires_at,
    )


def list_topics(
    coral_dir: str | Path,
    *,
    current_eval: int,
    quorum: int = 2,
    default_ttl: int = 30,
) -> list[TopicStatus]:
    """Return one TopicStatus per topic that has at least one claim.

    Topics with status ``unknown`` are not returned (they have no claims).
    Result is sorted by topic slug for stable output.
    """
    if quorum < 1:
        quorum = 1

    by_topic: dict[str, list[Claim]] = {}
    for c in _collect_claims(coral_dir, default_ttl=default_ttl):
        by_topic.setdefault(c.topic, []).append(c)

    statuses = [
        _classify(claims, current_eval=current_eval, quorum=quorum)
        for claims in by_topic.values()
    ]
    statuses.sort(key=lambda s: s.topic)
    return statuses


def topic_status(
    topic: str,
    coral_dir: str | Path,
    *,
    current_eval: int,
    quorum: int = 2,
    default_ttl: int = 30,
) -> TopicStatus:
    """Status for a specific topic.  Returns level=``unknown`` if no claims."""
    validate_slug(topic)
    matches = [
        c
        for c in _collect_claims(coral_dir, default_ttl=default_ttl)
        if c.topic == topic
    ]
    if not matches:
        return TopicStatus(topic=topic, level="unknown")
    return _classify(matches, current_eval=current_eval, quorum=quorum)


def find_consensus(
    coral_dir: str | Path,
    *,
    current_eval: int,
    quorum: int = 2,
    default_ttl: int = 30,
) -> list[TopicStatus]:
    """Topics where ≥quorum distinct agents have active claims."""
    return [
        s
        for s in list_topics(
            coral_dir,
            current_eval=current_eval,
            quorum=quorum,
            default_ttl=default_ttl,
        )
        if s.level == "consensus"
    ]


def find_disputed(
    coral_dir: str | Path,
    *,
    current_eval: int,
    quorum: int = 2,
    default_ttl: int = 30,
) -> list[TopicStatus]:
    """Topics that are ``disputed`` or ``stale`` — single voice or expired.

    These are the ones a skeptic agent should consider re-testing: they were
    claimed dead by one agent (and never confirmed) or the claim has aged out.
    """
    return [
        s
        for s in list_topics(
            coral_dir,
            current_eval=current_eval,
            quorum=quorum,
            default_ttl=default_ttl,
        )
        if s.level in ("disputed", "stale")
    ]
