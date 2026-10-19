"""The check bank: immutable, versioned, published by one writer under a lock.

Lives under ``<private_dir>/router_checks/``:

    versions/v{n}.json     immutable bank snapshots (v1 is the fixed suite)
    current                pointer to the active version number
    checkpoints.jsonl      one row per checkpoint decision: published / abstained /
                           blocked, with every proposal and its admission result
    deliveries.jsonl       one row per evaluation whose feedback named a bank
                           version: what was written to whom, and when
    proposals/             archived proposer contexts (prompt, staged evidence,
                           raw response), one directory per checkpoint
    bank.lock

An evaluation reads the current version once, under the lock, and is scored
against exactly that version even if a publication lands while it runs. A
version file is never rewritten; a publication writes v{n+1} and moves the
pointer, so a partially written bank cannot be observed.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_write(path: Path, data: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".bank.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(data)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def bank_sha256(checks: list[dict[str, Any]]) -> str:
    canon = json.dumps([c["id"] for c in checks], separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


class CheckBank:
    def __init__(self, private_dir: str | Path) -> None:
        self.root = Path(private_dir) / "router_checks"
        self.versions_dir = self.root / "versions"
        self.proposals_dir = self.root / "proposals"
        for d in (self.root, self.versions_dir, self.proposals_dir):
            d.mkdir(parents=True, exist_ok=True)
        self._current = self.root / "current"
        self._checkpoints = self.root / "checkpoints.jsonl"
        self._deliveries = self.root / "deliveries.jsonl"
        self._lock = self.root / "bank.lock"

    @contextmanager
    def locked(self) -> Iterator[None]:
        self._lock.touch(exist_ok=True)
        with open(self._lock, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    # -- versions ----------------------------------------------------------

    def current_version(self) -> int | None:
        try:
            return int(self._current.read_text().strip())
        except (OSError, ValueError):
            return None

    def load(self, version: int) -> dict[str, Any] | None:
        try:
            return json.loads((self.versions_dir / f"v{version}.json").read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def load_current(self) -> dict[str, Any] | None:
        v = self.current_version()
        return self.load(v) if v is not None else None

    def all_versions(self) -> list[int]:
        out = []
        for p in self.versions_dir.glob("v*.json"):
            try:
                out.append(int(p.stem[1:]))
            except ValueError:
                continue
        return sorted(out)

    def publish(self, checks: list[dict[str, Any]], *, meta: dict[str, Any]) -> dict[str, Any]:
        """Write the next version containing ``checks`` in full; immutable once written."""
        cur = self.load_current()
        version = 1 if cur is None else int(cur["version"]) + 1
        path = self.versions_dir / f"v{version}.json"
        if path.exists():
            raise ValueError(f"bank v{version} already exists; versions are immutable")
        snapshot = {
            "version": version,
            "parent_version": None if cur is None else cur["version"],
            "parent_sha256": None if cur is None else cur["sha256"],
            "sha256": bank_sha256(checks),
            "created_at": utcnow(),
            "n_checks": len(checks),
            "checks": checks,
            **meta,
        }
        _atomic_write(path, json.dumps(snapshot, indent=2, sort_keys=True))
        _atomic_write(self._current, str(version))
        return snapshot

    # -- records -----------------------------------------------------------

    def record_checkpoint(self, row: dict[str, Any]) -> None:
        with open(self._checkpoints, "a") as f:
            f.write(json.dumps({"recorded_at": utcnow(), **row}, sort_keys=True) + "\n")

    def checkpoints(self) -> list[dict[str, Any]]:
        if not self._checkpoints.exists():
            return []
        rows = []
        for line in self._checkpoints.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def checkpoints_evaluated(self) -> int:
        """Checkpoints consumed so far, whatever their status."""
        return sum(1 for r in self.checkpoints() if r.get("checkpoint_index") is not None)

    def record_delivery(self, row: dict[str, Any]) -> None:
        """A bank version was named in feedback written for one attempt.

        ``feedback_written`` is the claim, no more: the text went into the
        attempt record the submitting agent reads back. Whether the agent read
        it is not observable here.
        """
        with open(self._deliveries, "a") as f:
            f.write(
                json.dumps(
                    {"recorded_at": utcnow(), "status": "feedback_written", **row}, sort_keys=True
                )
                + "\n"
            )

    def deliveries(self) -> list[dict[str, Any]]:
        if not self._deliveries.exists():
            return []
        return [
            json.loads(line) for line in self._deliveries.read_text().splitlines() if line.strip()
        ]

    def proposal_dir(self, checkpoint_index: int) -> Path:
        d = self.proposals_dir / f"checkpoint_{checkpoint_index}_{utcnow().replace(':', '')}"
        d.mkdir(parents=True, exist_ok=False)
        return d
