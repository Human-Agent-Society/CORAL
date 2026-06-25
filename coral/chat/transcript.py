"""Transcript persistence for chat sessions (P4).

Each session's frames are appended to ``<chat_home>/<session_id>/transcript.jsonl``
(one JSON frame per line) alongside a ``meta.json``, so the conversation
survives a dashboard restart and can be read back for history. (Resuming a
dead session's `claude` process is out of scope — the subprocess dies with
the dashboard; this only preserves the transcript.)
"""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def chat_home() -> Path:
    """Root dir for persisted chat sessions.

    Honors ``$CORAL_CHAT_HOME`` (full path override, used in tests) and
    ``$XDG_CONFIG_HOME``, falling back to ``~/.config/coral/chat/`` — matching
    the convention in ``coral.user_agents.user_config_path``.
    """
    override = os.environ.get("CORAL_CHAT_HOME")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "coral" / "chat"


class ChatTranscript:
    """Append-only JSONL transcript for one session."""

    def __init__(self, session_id: str, root: Path | None = None) -> None:
        self.session_id = session_id
        self.dir = (root or chat_home()) / session_id
        self.transcript_path = self.dir / "transcript.jsonl"
        self.meta_path = self.dir / "meta.json"
        self._lock = threading.Lock()
        self._fh: Any = None

    def open(self, meta: dict[str, Any] | None = None) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {
            "session_id": self.session_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        if meta:
            record.update(meta)
        tmp = self.meta_path.parent / (self.meta_path.name + ".tmp")
        tmp.write_text(json.dumps(record, indent=2))
        tmp.replace(self.meta_path)
        self._fh = open(self.transcript_path, "a", buffering=1)

    def append(self, frame: dict[str, Any]) -> None:
        with self._lock:
            if self._fh is None:
                return
            self._fh.write(json.dumps(frame) + "\n")

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.close()
                finally:
                    self._fh = None


def read_meta(session_id: str, root: Path | None = None) -> dict[str, Any] | None:
    path = (root or chat_home()) / session_id / "meta.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def read_transcript(session_id: str, root: Path | None = None) -> list[dict[str, Any]]:
    path = (root or chat_home()) / session_id / "transcript.jsonl"
    if not path.exists():
        return []
    frames: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            frames.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return frames


def list_sessions(root: Path | None = None) -> list[dict[str, Any]]:
    base = root or chat_home()
    if not base.exists():
        return []
    out: list[dict[str, Any]] = []
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        out.append(read_meta(d.name, root=base) or {"session_id": d.name})
    out.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return out
