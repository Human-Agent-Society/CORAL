"""Atomic eval counter using file locking."""

from __future__ import annotations

import fcntl
from pathlib import Path


def increment_eval_count(coral_dir: Path) -> int:
    """Increment and return the eval counter, using fcntl.flock for atomicity."""
    counter_file = coral_dir / "public" / "eval_count"
    lock_file = coral_dir / "public" / "eval_count.lock"
    lock_file.touch(exist_ok=True)

    with open(lock_file) as fd:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            count = int(counter_file.read_text().strip()) if counter_file.exists() else 0
        except ValueError:
            count = 0
        count += 1
        counter_file.write_text(str(count))

    return count
