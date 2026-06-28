#!/usr/bin/env python3
"""unattributed.py — List notes that lack a ``creator:`` frontmatter field.

Usage:
    python unattributed.py [NOTES_DIR]

Walks ``.coral/public/notes/`` (or the given directory) and prints the
relative path of every user-authored note whose frontmatter is missing,
empty, or blank for ``creator:``.

Notes that land here are invisible to every team-level process that
filters by author — ``coral.hub.notes.notes_by``, the consolidate
roster, the librarian subagent, migration attribution. The hub still
loads them and the list view renders them as ``(unknown)``, but they
don't show up in team aggregations until someone appends a ``creator:``
line to the frontmatter.

Two use cases:
- An agent at the end of a write cycle running it on their own notes
  to catch a forgotten stamp.
- The consolidate heartbeat's roster-audit step calling it on the
  whole notes/ tree to surface orphan files for the team.

Self-contained: no imports from coral.* so the script ships intact
inside .coral/public/skills/create-notes/scripts/ on every island.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DEFAULT_NOTES_DIR = ".coral/public/notes"

SYSTEM_FILENAMES = {"notes.md", "index.md"}
SYSTEM_TOP_LEVEL_DIRS = {"raw"}


def _is_user_note(p: Path, notes_root: Path) -> bool:
    if p.name in SYSTEM_FILENAMES or p.name.startswith("_"):
        return False
    rel = p.relative_to(notes_root)
    return not (rel.parts and rel.parts[0] in SYSTEM_TOP_LEVEL_DIRS)


def _iter_user_note_files(notes_root: Path) -> list[Path]:
    files: list[Path] = []
    for root, dirs, names in os.walk(notes_root):
        root_path = Path(root)
        if root_path == notes_root:
            dirs[:] = sorted(d for d in dirs if d not in SYSTEM_TOP_LEVEL_DIRS)
        else:
            dirs.sort()
        for name in sorted(names):
            if name.endswith(".md"):
                p = root_path / name
                if _is_user_note(p, notes_root):
                    files.append(p)
    return files


def _creator_field(text: str) -> str:
    """Return the trimmed value of ``creator:`` from a frontmatter block, or
    "" if missing / blank / no frontmatter at all. YAML-free so the script
    runs in any Python interpreter."""
    if not text.startswith("---"):
        return ""
    end = text.find("---", 3)
    if end == -1:
        return ""
    for raw in text[3:end].splitlines():
        line = raw.strip()
        if line.startswith("creator:"):
            return line.split(":", 1)[1].strip()
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "notes_dir",
        nargs="?",
        default=DEFAULT_NOTES_DIR,
        help=f"Notes directory (default: {DEFAULT_NOTES_DIR})",
    )
    ap.add_argument(
        "--count-only",
        action="store_true",
        help="Print only the count of unattributed notes",
    )
    args = ap.parse_args()

    root = Path(args.notes_dir)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    missing: list[Path] = []
    for md in _iter_user_note_files(root):
        try:
            text = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not _creator_field(text):
            missing.append(md)

    if args.count_only:
        print(len(missing))
        return 0

    if not missing:
        print(f"all notes under {root} have a creator:")
        return 0

    print(f"{len(missing)} note(s) under {root} missing a non-blank creator:")
    for p in missing:
        print(f"  {p.relative_to(root).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
