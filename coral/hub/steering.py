"""Steer-on-resume queue over .coral/public/steering/."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

ActionKind = Literal["continue_from", "mark_best"]


@dataclass
class SteeringAction:
    """A queued dashboard steering action."""

    hash: str
    instruction: str = ""
    id: str = ""
    created_at: str = ""
    applied_at: str | None = None
    kind: ActionKind = "continue_from"

    def __post_init__(self) -> None:
        if not self.id:
            self.id = uuid4().hex
        if not self.created_at:
            self.created_at = _now()

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "hash": self.hash,
            "created_at": self.created_at,
            "applied_at": self.applied_at,
        }
        if self.instruction:
            data["instruction"] = self.instruction
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SteeringAction:
        kind = data["kind"]
        if kind == "continue_from":
            return ContinueFromAction(
                hash=data["hash"],
                instruction=data.get("instruction", ""),
                id=data.get("id", ""),
                created_at=data.get("created_at", ""),
                applied_at=data.get("applied_at"),
            )
        if kind == "mark_best":
            return MarkBestAction(
                hash=data["hash"],
                id=data.get("id", ""),
                created_at=data.get("created_at", ""),
                applied_at=data.get("applied_at"),
            )
        raise ValueError(f"unknown steering action kind: {kind!r}")


@dataclass
class ContinueFromAction(SteeringAction):
    kind: ActionKind = "continue_from"


@dataclass
class MarkBestAction(SteeringAction):
    kind: ActionKind = "mark_best"
    instruction: str = ""


def enqueue(coral_dir: str | Path, action: SteeringAction) -> SteeringAction:
    """Append an action to the pending queue using tmp + rename."""
    path = _action_path(coral_dir, action.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(path, action.to_dict())
    return action


def read_pending(coral_dir: str | Path) -> list[SteeringAction]:
    """Return unapplied queued actions sorted by creation time."""
    actions: list[SteeringAction] = []
    for path in sorted(_steering_dir(coral_dir).glob("*.json")):
        try:
            action = SteeringAction.from_dict(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError):
            continue
        if action.applied_at is None:
            actions.append(action)
    actions.sort(key=lambda a: a.created_at)
    return actions


def mark_applied(coral_dir: str | Path, action_id: str) -> bool:
    """Mark one queued action applied. Returns False if it is missing or malformed."""
    path = _action_path(coral_dir, action_id)
    if not path.exists():
        return False
    try:
        action = SteeringAction.from_dict(json.loads(path.read_text()))
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError):
        return False
    action.applied_at = _now()
    _atomic_write_json(path, action.to_dict())
    return True


def _steering_dir(coral_dir: str | Path) -> Path:
    return Path(coral_dir) / "public" / "steering"


def _action_path(coral_dir: str | Path, action_id: str) -> Path:
    return _steering_dir(coral_dir) / f"{action_id}.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
