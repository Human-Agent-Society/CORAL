"""Task validation — checks that a task directory is well-formed.

Called automatically by `coral start` and `coral validate`.
"""

from __future__ import annotations

from pathlib import Path

from coral.task.validation import validate_task as validate_task_report


def validate_task(task_dir: Path) -> list[str]:
    """Validate a task directory. Returns a list of error strings (empty = valid)."""
    return validate_task_report(task_dir).error_messages
