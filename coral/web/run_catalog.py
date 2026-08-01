"""Discover CORAL run catalogs that belong to the current project."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "node_modules",
    }
)


def find_catalog_root(start: Path, current_results_dir: Path) -> Path:
    """Return the nearest Git root, falling back to the launch directory.

    A project root gives the dashboard a useful, bounded area to search.  The
    fallback keeps the feature working for non-Git task collections without
    broadening discovery to a user's home directory.
    """
    start = start.resolve()
    current_results_dir = current_results_dir.resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists() and current_results_dir.is_relative_to(candidate):
            return candidate

    if current_results_dir.is_relative_to(start):
        return start
    return current_results_dir.parent


def results_dir_id(results_dir: Path) -> str:
    """Return a stable, opaque browser-facing identifier for a results root."""
    value = str(results_dir.resolve()).encode()
    return hashlib.sha256(value).hexdigest()[:16]


def results_dir_label(results_dir: Path, catalog_root: Path) -> str:
    """Return a compact project-relative label for the run selector."""
    results_dir = results_dir.resolve()
    catalog_root = catalog_root.resolve()
    try:
        relative = results_dir.relative_to(catalog_root)
    except ValueError:
        return results_dir.name
    return str(relative) if relative.parts else results_dir.name


def discover_results_dirs(catalog_root: Path, current_results_dir: Path) -> tuple[Path, ...]:
    """Find populated ``results`` catalogs below ``catalog_root``.

    Discovery stops at each catalog instead of descending into cloned repos or
    dependency trees stored inside a run.  The current catalog is always
    included, including when it has a custom name rather than ``results``.
    """
    catalog_root = catalog_root.resolve()
    current_results_dir = current_results_dir.resolve()
    discovered = {current_results_dir}

    if catalog_root.is_dir():
        for raw_root, dirnames, _filenames in os.walk(catalog_root, topdown=True):
            root = Path(raw_root)
            dirnames[:] = [
                name
                for name in dirnames
                if name not in _IGNORED_DIRS and not (root / name).is_symlink()
            ]

            resolved_root = root.resolve()
            if resolved_root == current_results_dir:
                dirnames.clear()
                continue

            if root.name == "results":
                if _contains_run(root):
                    discovered.add(resolved_root)
                dirnames.clear()

    return tuple(sorted(discovered, key=lambda path: results_dir_label(path, catalog_root).lower()))


def _contains_run(results_dir: Path) -> bool:
    """Return whether a directory has the ``task/run/.coral`` layout."""
    try:
        for task_dir in results_dir.iterdir():
            if not task_dir.is_dir() or task_dir.is_symlink():
                continue
            for run_dir in task_dir.iterdir():
                if run_dir.is_dir() and not run_dir.is_symlink() and (run_dir / ".coral").is_dir():
                    return True
    except OSError:
        return False
    return False
