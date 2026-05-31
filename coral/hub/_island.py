"""Per-island base-path resolver.

Single-island runs (no ``.coral/islands/`` subdir) return ``coral_dir/public``
regardless of the ``island_id`` argument — this preserves today's layout
exactly and makes the optional ``island_id`` parameter safe to add to every
hub function without changing behavior.

Multi-island runs (``.coral/islands/`` exists) return
``coral_dir/islands/<island_id>``, and require ``island_id`` to be set.
"""

from __future__ import annotations

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
        return islands_dir / str(island_id)
    return coral_dir / "public"
