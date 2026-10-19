"""Append-only intervention-delivery records.

An intervention event establishes that CORAL inserted a payload into a model
context.  It deliberately does *not* claim that the model attended to,
understood, or acted on the payload.  Those are separate analysis questions.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
RELATIVE_LOG = Path("private") / "research" / "intervention_events.jsonl"


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _event_id(event: dict[str, Any]) -> str:
    """A content address for one delivery, including its timestamp.

    Two genuinely repeated insertions of the same payload differ in
    ``delivered_at`` and therefore stay separately visible, which is the
    behaviour the ledger needs. Because the timestamp defaults to now, this
    is an identifier, not a duplicate-suppression key.
    """
    identity = {
        "agent_id": event.get("agent_id"),
        "attempt_id": event.get("attempt_id"),
        "channel": event.get("channel"),
        "prompt_source": event.get("prompt_source"),
        "content_sha256": event.get("content_sha256"),
        "delivered_at": event.get("delivered_at"),
    }
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def append_intervention_event(coral_dir: str | Path, event: dict[str, Any]) -> dict[str, Any]:
    """Persist one prompt dispatch and return the stored payload.

    A call that supplies its own identity -- an explicit ``event_id`` or an
    explicit ``delivered_at`` -- is asserting that it may be a replay, and is
    de-duplicated. A call that supplies neither is a fresh delivery and is
    always appended, because two genuine insertions of the same payload are
    two events and must both remain visible. Only the first case pays for a
    scan of the log, which keeps the live recording path off it entirely.

    The full payload is kept in private research state so later analyses can
    verify the hash without exposing grader feedback to agents through a new
    public channel.
    """
    content = event.get("content")
    if not isinstance(content, str) or not content:
        raise ValueError("intervention events require non-empty string content")
    if not event.get("agent_id"):
        raise ValueError("intervention events require agent_id")
    if not event.get("channel"):
        raise ValueError("intervention events require channel")

    explicit_id = event.get("event_id")
    caller_supplied_identity = bool(explicit_id or event.get("delivered_at"))
    payload = {
        **event,
        "schema": SCHEMA_VERSION,
        "delivered_at": event.get("delivered_at") or utcnow(),
        "delivery_status": "dispatched_to_runtime",
        "content_sha256": content_sha256(content),
        "content_chars": len(content),
    }
    payload["event_id"] = explicit_id or _event_id(payload)

    path = Path(coral_dir) / RELATIVE_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with open(lock_path, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            # Only a caller that pinned its own identity claims replay safety,
            # so only that case pays for a scan. Everything else is new.
            if caller_supplied_identity and _has_event_id(path, payload["event_id"]):
                return payload
            with open(path, "a", encoding="utf-8") as out:
                out.write(json.dumps(payload, sort_keys=True) + "\n")
                out.flush()
            return payload
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _has_event_id(path: Path, event_id: str) -> bool:
    if not path.exists():
        return False
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                if json.loads(line).get("event_id") == event_id:
                    return True
            except json.JSONDecodeError:
                continue
    return False


def load_intervention_events(coral_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(coral_dir) / RELATIVE_LOG
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return sorted(events, key=lambda e: (e.get("delivered_at") or "", e.get("event_id") or ""))
