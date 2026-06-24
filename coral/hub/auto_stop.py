"""Run-level auto-stop state stored under .coral/public/."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

AUTO_STOP_FILENAME = "auto_stop.json"


def auto_stop_path(coral_dir: str | Path) -> Path:
    """Return the public auto-stop state path for a run."""
    return Path(coral_dir) / "public" / AUTO_STOP_FILENAME


def write_auto_stop(coral_dir: str | Path, payload: dict[str, Any]) -> Path:
    """Persist an auto-stop reason atomically."""
    path = auto_stop_path(coral_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{AUTO_STOP_FILENAME}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return path


def read_auto_stop(coral_dir: str | Path) -> dict[str, Any] | None:
    """Read the auto-stop state, returning None when absent or malformed."""
    path = auto_stop_path(coral_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None
