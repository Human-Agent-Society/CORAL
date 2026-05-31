"""Per-island base-path resolver.

Single-island runs (no ``.coral/islands/`` subdir) return ``coral_dir/public``
regardless of the ``island_id`` argument — this preserves today's layout
exactly and makes the optional ``island_id`` parameter safe to add to every
hub function without changing behavior.

Multi-island runs (``.coral/islands/`` exists) return
``coral_dir/islands/<island_id>``, and require ``island_id`` to be set.
"""

from __future__ import annotations

import os
from pathlib import Path


def island_root(coral_dir: str | Path, island_id: str | int | None) -> Path:
    """Resolve the per-island base path under ``coral_dir``.

    Returns ``coral_dir/public`` in single-island mode (no ``islands/`` subdir
    on disk, regardless of the ``island_id`` argument). Returns
    ``coral_dir/islands/<island_id>`` in multi-island mode; raises if
    ``island_id`` is None there.
    """
    coral_dir = Path(coral_dir)
    islands_dir = coral_dir / "islands"
    if islands_dir.exists():
        if island_id is None:
            raise ValueError(
                "island_id is required in multi-island runs "
                f"({islands_dir} exists on disk)"
            )
        id_str = str(island_id)
        if (
            not id_str
            or "/" in id_str
            or os.sep in id_str
            or id_str == ".."
        ):
            raise ValueError(
                f"island_id {island_id!r} is invalid: must be a non-empty "
                "string containing no path separators or '..'"
            )
        return islands_dir / id_str
    return coral_dir / "public"
