"""Tests for multi-island layout primitives."""

import tempfile
from pathlib import Path

import pytest

from coral.hub._island import island_root


def test_island_root_single_island_no_islands_dir():
    """When .coral/islands/ does not exist, island_root returns public/ regardless of id."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        # No islands/ dir created
        assert island_root(coral_dir, None) == coral_dir / "public"
        # Even with island_id, single-island layout returns public/
        assert island_root(coral_dir, "0") == coral_dir / "public"


def test_island_root_multi_island_with_id():
    """When islands/ exists, island_root returns the per-island subdir."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "islands").mkdir()
        assert island_root(coral_dir, "0") == coral_dir / "islands" / "0"
        assert island_root(coral_dir, "3") == coral_dir / "islands" / "3"
        # Integer ids are stringified
        assert island_root(coral_dir, 2) == coral_dir / "islands" / "2"


def test_island_root_multi_island_requires_id():
    """In multi-island layout, island_id=None is an error."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "islands").mkdir()
        with pytest.raises(ValueError, match="island_id is required"):
            island_root(coral_dir, None)


def test_island_root_rejects_invalid_ids():
    """Reject empty, separator-bearing, and traversal-bearing island_ids."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "islands").mkdir()
        for bad in ("", "..", "../escape", "0/notes", "a/b"):
            with pytest.raises(ValueError, match="invalid"):
                island_root(coral_dir, bad)


def test_island_root_accepts_integer_zero():
    """Integer 0 (often a valid first-island id) must round-trip cleanly."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "islands").mkdir()
        assert island_root(coral_dir, 0) == coral_dir / "islands" / "0"
