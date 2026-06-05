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
from collections.abc import Iterator
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
                f"island_id is required in multi-island runs ({islands_dir} exists on disk)"
            )
        id_str = str(island_id)
        if not id_str or "/" in id_str or os.sep in id_str or id_str == "..":
            raise ValueError(
                f"island_id {island_id!r} is invalid: must be a non-empty "
                "string containing no path separators or '..'"
            )
        return islands_dir / id_str
    return coral_dir / "public"


def island_id_from_agent_id(agent_id: str) -> str | None:
    """Extract the island id from a partition-prefixed agent id.

    Partitioning writes agent ids as ``<island_id>-agent-<n>`` (e.g.
    ``0-agent-1``); a bare ``agent-N`` (no prefix) means single-island and
    returns None. The prefix is a stable birth-lineage marker, not a current
    island marker after migration. Use it only for lineage display or
    backwards-compatible birth-island guesses, never as authoritative
    current-location routing.
    """
    if "-" not in agent_id:
        return None
    head = agent_id.split("-", 1)[0]
    # Heuristic: an island id is a short non-negative int; anything else is
    # an ordinary agent name and we leave it for the caller to interpret.
    return head if head.isdigit() else None


def all_view_roots(coral_dir: str | Path) -> list[Path]:
    """Roots a "view the whole run" command should iterate.

    Returns ``[coral_dir/public]`` in single-island mode, and a sorted list
    of ``coral_dir/islands/<id>`` paths in multi-island mode. Use this from
    CLI commands and hub helpers that aggregate across islands when the
    caller hasn't pinned a specific one.
    """
    coral_dir = Path(coral_dir)
    islands_dir = coral_dir / "islands"
    if islands_dir.exists():
        return sorted(d for d in islands_dir.iterdir() if d.is_dir())
    return [coral_dir / "public"]


def iter_view_roots(coral_dir: str | Path) -> Iterator[Path]:
    """Same as ``all_view_roots`` but as a generator (avoid the list copy)."""
    yield from all_view_roots(coral_dir)
