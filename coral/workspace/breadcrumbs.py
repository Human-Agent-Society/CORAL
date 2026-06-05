"""Helpers for locating CORAL worktree breadcrumbs."""

from __future__ import annotations

from pathlib import Path


def find_breadcrumb_file(name: str, start: str | Path | None = None) -> Path | None:
    """Walk upward from ``start`` looking for a breadcrumb file named ``name``."""
    cur = Path.cwd() if start is None else Path(start)
    cur = cur.resolve()
    while True:
        candidate = cur / name
        if candidate.exists():
            return candidate
        if cur == cur.parent:
            return None
        cur = cur.parent


def find_coral_breadcrumb(start: str | Path | None = None) -> tuple[Path, Path] | None:
    """Return ``(coral_dir, breadcrumb_dir)`` for the nearest valid .coral_dir."""
    cur = Path.cwd() if start is None else Path(start)
    cur = cur.resolve()
    while True:
        breadcrumb = cur / ".coral_dir"
        if breadcrumb.exists():
            try:
                coral_dir = Path(breadcrumb.read_text().strip()).resolve()
            except (OSError, ValueError):
                coral_dir = None
            if coral_dir is not None and coral_dir.is_dir():
                return coral_dir, cur
        if cur == cur.parent:
            return None
        cur = cur.parent


def read_island_breadcrumb(coral_dir: Path, breadcrumb_dir: Path) -> str | None:
    """Read and validate the island breadcrumb adjacent to a .coral_dir file."""
    island_file = breadcrumb_dir / ".coral_island"
    if not island_file.exists():
        return None
    try:
        island_id = island_file.read_text().strip()
    except OSError:
        return None
    if island_id and (coral_dir / "islands" / island_id).is_dir():
        return island_id
    return None
