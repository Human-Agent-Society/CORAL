"""Rubric state: immutable snapshots plus an append-only event ledger.

Two invariants, and nothing else:

* **Snapshots are immutable.** ``versions/v{n}.json`` is written once. Any
  change to the criteria set publishes a new version. A score is always recorded against the version it was actually
  scored under.
* **Events are the only source of truth for scores.** ``evaluate()`` writes one
  event per evaluation and returns. An event counts as an observation exactly
  when its attempt record has been finalized by CORAL's daemon. That is a pure
  function of what is on disk, so there is no cache to go stale, no "applied"
  bookkeeping to corrupt, and nothing to replay.

This replaced a design with three state files (observations cache, applied-ids
ledger, criterion ledger) that could disagree with one another and needed a
rebuild routine and a replay check to keep honest. Fewer files, stronger
guarantees.
"""

from __future__ import annotations

import dataclasses
import fcntl
import hashlib
import json
import logging
import re
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 3


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def normalize_name(name: str) -> str:
    """Casefold and strip punctuation, so "Accessibility & Semantic Markup" and
    "accessibility and semantic-markup" collide. Enough to stop cosmetic
    re-admission of a criterion; whether two differently worded criteria measure
    the same thing is analysis work, not runtime machinery."""
    s = name.casefold().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


# ============================================================================
# Value types
# ============================================================================


@dataclass
class Criterion:
    """A criterion *definition*. Carries no scores; those live in events."""

    name: str
    description: str
    weight: float = 1.0
    anchor: bool = False
    added_in_version: int = 1
    # Where the idea came from: task_specification | agent_note |
    # evaluator_feedback | evolution_agent_inference(<trigger>)
    provenance: str = "task_specification"
    #: The proposer's citation of the concrete pre-publication deficiency this
    #: criterion addresses — the solutions-to-evaluator half of the loop.
    #: Empty for seed criteria.
    cited_evidence: str = ""
    #: The source the quote was taken from: an attempt id for the adaptive arm,
    #: "brief" for the yoked arm. Persisted so the exact sentence that passed
    #: the admission gate can be audited after the run; validating it and then
    #: discarding it would leave the gate unfalsifiable.
    cited_source_id: str = ""
    #: The verbatim text quoted from that source.
    quote: str = ""
    source_attempt_ids: list[str] = field(default_factory=list)
    source_note_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Criterion:
        return cls(
            name=d["name"],
            description=d.get("description", ""),
            weight=float(d.get("weight", 1.0)),
            anchor=bool(d.get("anchor", False)),
            added_in_version=int(d.get("added_in_version", 1)),
            provenance=d.get("provenance", "unknown"),
            cited_evidence=d.get("cited_evidence", ""),
            cited_source_id=d.get("cited_source_id", ""),
            quote=d.get("quote", ""),
            source_attempt_ids=list(d.get("source_attempt_ids", [])),
            source_note_ids=list(d.get("source_note_ids", [])),
        )

    def to_criteria_arg(self) -> dict[str, Any]:
        """The shape a criteria-driven inner grader reads from ``args``."""
        return {"name": self.name, "weight": self.weight, "description": self.description}


@dataclass
class RubricSnapshot:
    """One immutable rubric version."""

    version: int
    criteria: list[Criterion]
    trigger: str = "initial"
    notes: str = ""
    created_at: str = ""
    parent_version: int | None = None
    # The attempt whose evaluation caused this version to exist — the
    # provenance the proposal's "which agent's output triggered each
    # evolution" analysis needs.
    created_by_attempt_id: str | None = None
    created_by_agent_id: str | None = None

    def anchors(self) -> list[Criterion]:
        return [c for c in self.criteria if c.anchor]

    def by_name(self, name: str) -> Criterion | None:
        return next((c for c in self.criteria if c.name == name), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "version": self.version,
            "criteria": [c.to_dict() for c in self.criteria],
            "trigger": self.trigger,
            "notes": self.notes,
            "created_at": self.created_at,
            "parent_version": self.parent_version,
            "created_by_attempt_id": self.created_by_attempt_id,
            "created_by_agent_id": self.created_by_agent_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RubricSnapshot:
        return cls(
            version=int(d["version"]),
            criteria=[Criterion.from_dict(c) for c in d.get("criteria", [])],
            trigger=d.get("trigger", "initial"),
            notes=d.get("notes", ""),
            created_at=d.get("created_at", ""),
            parent_version=d.get("parent_version"),
            created_by_attempt_id=d.get("created_by_attempt_id"),
            created_by_agent_id=d.get("created_by_agent_id"),
        )


@dataclass
class Observation:
    """One finalized attempt's scores, bound to the version actually used.

    ``scores`` may omit criteria the evaluator failed to score; consumers must
    handle that explicitly rather than assume density.
    """

    attempt_id: str
    rubric_version: int
    aggregated: float
    scores: dict[str, float]
    agent_id: str | None = None
    timestamp: str = ""
    evaluator_meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_event(cls, e: dict[str, Any]) -> Observation:
        return cls(
            attempt_id=e["attempt_id"],
            rubric_version=int(e["rubric_version_scored"]),
            aggregated=float(e["aggregated"]),
            scores={k: float(v) for k, v in (e.get("scores") or {}).items()},
            agent_id=e.get("agent_id"),
            timestamp=e.get("written_at", ""),
            evaluator_meta=dict(e.get("evaluator_meta") or {}),
        )


# ============================================================================
# The store
# ============================================================================


class EvolutionStore:
    """Filesystem-backed rubric state under ``<private_dir>/evolving/``.

    Layout::

        versions/v{n}.json   immutable snapshots
        events/{attempt}.json  one per evaluation (scored or failed)
        rejected.jsonl       proposals that were filtered out, for recurrence analysis
        RUBRIC_CHANGELOG.md  human-readable narrative
        current_version      pointer
        evolving.lock

    Mutating entry points must be called inside ``locked()``.
    """

    def __init__(self, private_dir: str | Path) -> None:
        self.root = Path(private_dir) / "evolving"
        self.versions_dir = self.root / "versions"
        self.events_dir = self.root / "events"
        for d in (self.root, self.versions_dir, self.events_dir):
            d.mkdir(parents=True, exist_ok=True)
        self._current_path = self.root / "current_version"
        self._rejected_path = self.root / "rejected.jsonl"
        self._changelog_path = self.root / "RUBRIC_CHANGELOG.md"
        self._lock_path = self.root / "evolving.lock"

    @contextmanager
    def locked(self) -> Iterator[None]:
        self._lock_path.touch(exist_ok=True)
        with open(self._lock_path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    # -- snapshots --------------------------------------------------------

    def current_version_number(self) -> int | None:
        try:
            return int(self._current_path.read_text().strip())
        except (OSError, ValueError):
            return None

    def load_snapshot(self, version: int) -> RubricSnapshot | None:
        p = self.versions_dir / f"v{version}.json"
        try:
            return RubricSnapshot.from_dict(json.loads(p.read_text()))
        except (OSError, json.JSONDecodeError, KeyError):
            return None

    def load_current(self) -> RubricSnapshot | None:
        v = self.current_version_number()
        return self.load_snapshot(v) if v is not None else None

    def all_versions(self) -> list[int]:
        out = []
        for p in self.versions_dir.glob("v*.json"):
            try:
                out.append(int(p.stem[1:]))
            except ValueError:
                continue
        return sorted(out)

    def publish_snapshot(self, snap: RubricSnapshot) -> RubricSnapshot:
        p = self.versions_dir / f"v{snap.version}.json"
        if p.exists():
            raise ValueError(
                f"rubric v{snap.version} already exists; snapshots are immutable — "
                "publish a new version instead"
            )
        if not snap.created_at:
            snap.created_at = utcnow()
        _atomic_write(p, json.dumps(snap.to_dict(), indent=2))
        _atomic_write(self._current_path, str(snap.version))
        return snap

    # -- events -------------------------------------------------------------

    #: Event fields that record what an attempt was actually scored against.
    #: Once written they are the historical record and may never change.
    PROTECTED_EVENT_FIELDS = ("attempt_id", "rubric_version_scored", "scores", "aggregated")

    def write_event(
        self,
        event: dict[str, Any],
        is_finalized: Callable[[str], bool] | None = None,
    ) -> Path:
        """Write an attempt's evaluation event. First write wins, except orphans.

        Attempt finalization in `coral.hub.attempts` is first-write-wins, so
        this must be too. If it were not, a second grade of the same commit
        would leave the attempt record showing the first grade's score and the
        event ledger showing the second's — and every rubric decision is
        derived from the ledger, so the two sources of truth would silently
        disagree about what the rubric was responding to.

        **Orphans are the exception, and refusing them causes the very desync
        the rule exists to prevent.** A grader can write its event and then die
        before finalizing:

            grader A writes event 0.9, then dies (attempt still pending)
            grader B re-grades, its event 0.2 is refused, B finalizes 0.2
            -> event 0.9, attempt 0.2

        A prior event whose attempt is *not yet finalized* belongs to a grader
        that never completed, so it is not history — nothing was ever reported
        from it. The retry may replace it. Once the attempt has a terminal
        record, the event that produced it is history and is immutable.

        ``is_finalized`` supplies that test; omit it and every conflict is
        refused, which is the safe default for callers that are not re-grading
        under a claim. Callers that pass it must hold the attempt's claim (see
        ``hub.attempts.claim_attempt``), otherwise a concurrent grader could
        finalize between the check and the write.

        A byte-identical re-write is always a no-op.
        """
        attempt_id = event["attempt_id"]
        p = self.events_dir / f"{attempt_id}.json"
        lock_path = p.with_suffix(".json.lock")
        with open(lock_path, "a+") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                if p.exists():
                    try:
                        existing = json.loads(p.read_text())
                    except (OSError, json.JSONDecodeError):
                        existing = None
                    if existing is not None:
                        conflicts = [
                            k
                            for k in self.PROTECTED_EVENT_FIELDS
                            if k in event and existing.get(k) != event[k]
                        ]
                        if not conflicts:
                            return p
                        orphaned = is_finalized is not None and not is_finalized(attempt_id)
                        if not orphaned:
                            logger.error(
                                "refusing to overwrite event %s: conflicting %s "
                                "(kept aggregated=%r, discarded %r). Its attempt is already "
                                "finalized, so this event is history.",
                                attempt_id,
                                conflicts,
                                existing.get("aggregated"),
                                event.get("aggregated"),
                            )
                            return p
                        logger.warning(
                            "replacing orphan event %s (aggregated %r -> %r): its attempt was "
                            "never finalized, so the grader that wrote it died mid-grade.",
                            attempt_id,
                            existing.get("aggregated"),
                            event.get("aggregated"),
                        )
                payload = {"schema": SCHEMA_VERSION, "written_at": utcnow(), **event}
                _atomic_write(p, json.dumps(payload, indent=2))
                return p
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)

    def annotate_event(self, attempt_id: str, fields: dict[str, Any]) -> None:
        """Add derived facts (e.g. which version this attempt went on to
        create). Never touches what the attempt was scored against."""
        p = self.events_dir / f"{attempt_id}.json"
        try:
            event = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return
        for k in self.PROTECTED_EVENT_FIELDS:
            if k in fields:
                raise ValueError(f"refusing to rewrite protected event field {k!r}")
        event.update(fields)
        _atomic_write(p, json.dumps(event, indent=2))

    # -- trigger diagnostics and the publication schedule -------------------

    def write_trigger_decision(self, record: dict[str, Any]) -> None:
        """Append one structured record per gate evaluation.

        The design doc makes this a thesis artifact: it must be "sufficient to
        explain why the evaluator changed or did not change without
        reconstructing hidden state after the run". So it is written on every
        evaluation, whether or not anything fired, and it carries the gate
        blockers and every trigger's verdict — not just the winner.
        """
        path = self.root / "trigger_decisions.jsonl"
        with open(path, "a") as f:
            f.write(json.dumps({"written_at": utcnow(), **record}) + "\n")

    def load_trigger_decisions(self) -> list[dict[str, Any]]:
        path = self.root / "trigger_decisions.jsonl"
        if not path.exists():
            return []
        out = []
        for line in path.read_text().splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def publications(self) -> list[dict[str, Any]]:
        """Successful publications, oldest first, derived from the diagnostics.

        Derived rather than stored separately so the two can never disagree.
        """
        return [d for d in self.load_trigger_decisions() if d.get("published")]

    def checkpoints_evaluated(self, mode: str) -> int:
        """How many fixed checkpoints this arm has already evaluated.

        Counts every checkpoint that was looked at, whether or not it
        published — an abstention still consumes its checkpoint, or the next
        evaluation would just ask the same one again. One row per distinct
        ``checkpoint_index`` is expected; the lock held for the whole advance
        serializes writers, so concurrent workers cannot double-count one.
        """
        return len(
            {
                d["checkpoint_index"]
                for d in self.load_trigger_decisions()
                if d.get("mode") == mode and d.get("checkpoint_index") is not None
            }
        )

    def checkpoint_schedule_export(
        self, run_id: str, expected_checkpoints: list[int] | None = None
    ) -> dict[str, Any] | None:
        """The checkpoint-mode export, or None if this run used the variance
        triggers instead.

        Every evaluated checkpoint is included regardless of outcome, each
        tagged with an explicit ``status``:

        * ``published`` — the proposer's output survived every filter.
        * ``abstained`` — the proposer was invoked and found nothing
          admissible. Exposure the yoke must also receive, at zero criteria,
          not a gap to skip over.
        * ``blocked`` — the deadline or the rubric cap stopped the proposer
          from being invoked *at all*. This is not the same claim as
          "examined the evidence and found nothing" and must never be
          exported as an accepted count of zero indistinguishable from one.

        ``complete`` is false whenever ``expected_checkpoints`` is supplied and
        the run did not evaluate all of them (stopped early, or the run ended
        before its scored-observation count reached the last one) — the caller is
        expected to know, from its own task config, how many there should have
        been; without it, completeness cannot be checked from the log alone.
        A schedule that is incomplete or contains any ``blocked`` checkpoint
        is refused by the yoke loader (``EvolvingTaskGrader._yoked_schedule``)
        before it is ever replayed.
        """
        by_index: dict[int, dict[str, Any]] = {}
        for d in self.load_trigger_decisions():
            idx = d.get("checkpoint_index")
            if d.get("mode") == "adaptive" and idx is not None:
                by_index[idx] = d
        if not by_index:
            return None
        ordered = [by_index[i] for i in sorted(by_index)]
        checkpoints = [int(d["checkpoint_value"]) for d in ordered]
        accepted_counts = [int(d.get("accepted_count") or 0) for d in ordered]
        # Fail closed on a record with no explicit status (only possible from a
        # pre-status write): guess "blocked", never "abstained" — the entire
        # point of tagging status is that an unlabeled non-publication must
        # not be silently trusted as a clean examination that found nothing.
        statuses = [
            str(d.get("status") or ("published" if d.get("published") else "blocked"))
            for d in ordered
        ]
        complete = (
            True if expected_checkpoints is None else checkpoints == list(expected_checkpoints)
        )
        payload = {
            "source_run": run_id,
            "schedule_kind": "checkpoint",
            "checkpoints": checkpoints,
            "accepted_counts": accepted_counts,
            "statuses": statuses,
            "complete": complete,
        }
        hashed = {
            "checkpoints": checkpoints,
            "accepted_counts": accepted_counts,
            "statuses": statuses,
            "complete": complete,
        }
        payload["schedule_sha256"] = hashlib.sha256(
            json.dumps(hashed, sort_keys=True).encode()
        ).hexdigest()
        return payload

    def export_publication_schedule(
        self, run_id: str, expected_checkpoints: list[int] | None = None
    ) -> dict[str, Any]:
        """The schedule a yoke replays: every evaluated checkpoint with its
        outcome and admitted count, hashed. Raises if this run recorded no
        checkpoint decisions (nothing to replay)."""
        exported = self.checkpoint_schedule_export(run_id, expected_checkpoints)
        if exported is None:
            raise ValueError(f"run {run_id!r} recorded no checkpoint decisions; nothing to export")
        return exported

    def load_events(self) -> list[dict[str, Any]]:
        out = []
        for p in self.events_dir.glob("*.json"):
            try:
                out.append(json.loads(p.read_text()))
            except (OSError, json.JSONDecodeError):
                continue
        out.sort(key=lambda e: (e.get("written_at") or "", e.get("attempt_id") or ""))
        return out

    def observations(self, is_finalized: Callable[[str], bool]) -> list[Observation]:
        """Scored events whose attempt CORAL has finalized, oldest first.

        Derived on every call. An event for an attempt still ``pending`` is
        simply not an observation yet; it becomes one the moment the daemon
        finalizes the record. No state is written here.
        """
        return [
            Observation.from_event(e)
            for e in self.load_events()
            if e.get("outcome") == "scored" and is_finalized(e["attempt_id"])
        ]

    # -- rejected proposals (recurrence evidence) ---------------------------

    def record_rejected_proposal(self, name: str, description: str, reason: str) -> None:
        with open(self._rejected_path, "a") as f:
            f.write(
                json.dumps(
                    {
                        "name": name,
                        "normalized": normalize_name(name),
                        "description": description,
                        "reason": reason,
                        "at": utcnow(),
                    }
                )
                + "\n"
            )

    def rejected_proposals(self) -> list[dict[str, Any]]:
        try:
            return [
                json.loads(line) for line in self._rejected_path.read_text().splitlines() if line
            ]
        except OSError:
            return []

    def ever_seen_names(self) -> set[str]:
        """Normalized names of every criterion that has ever been active, derived
        from the snapshots themselves."""
        seen: set[str] = set()
        for v in self.all_versions():
            snap = self.load_snapshot(v)
            if snap is None:
                continue
            seen.update(normalize_name(c.name) for c in snap.criteria)
        return seen

    def recurrence_count(self, name: str) -> int:
        """Times this idea has already been admitted or proposed-and-rejected.
        Recurrence across independent checkpoints is recorded, not discarded."""
        key = normalize_name(name)
        admitted = 0
        for v in self.all_versions():
            snap = self.load_snapshot(v)
            if snap is None:
                continue
            admitted += sum(
                1
                for c in snap.criteria
                if normalize_name(c.name) == key and c.added_in_version == v
            )
        rejected = sum(1 for r in self.rejected_proposals() if r.get("normalized") == key)
        return admitted + rejected

    # -- changelog ----------------------------------------------------------

    def append_changelog(self, text: str) -> None:
        if not self._changelog_path.exists():
            self._changelog_path.write_text(
                "# Rubric Evolution Changelog\n\nImmutable snapshots; every score is bound "
                "to the version it was scored under.\n\n---\n\n"
            )
        with open(self._changelog_path, "a") as f:
            f.write(text)


def _atomic_write(path: Path, data: str) -> None:
    tmp = tempfile.NamedTemporaryFile(mode="w", dir=path.parent, suffix=".tmp", delete=False)
    try:
        tmp.write(data)
        tmp.flush()
        tmp.close()
        Path(tmp.name).rename(path)
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise
