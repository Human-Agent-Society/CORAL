#!/usr/bin/env python3
"""generate_index.py — Auto-generate index.md for a notes directory.

Usage: python generate_index.py [NOTES_DIR] [--dry-run]
Defaults to .coral/public/notes if no argument given.

Produces a navigable table of contents grouped by category (Research,
Experiments, Other). Skips raw/ (immutable sources) and meta files.
Uses atomic writes for safe concurrent access.
"""

import argparse
import os
import tempfile
from pathlib import Path

# Categories in display order. raw/ is excluded from the index.
CATEGORY_ORDER = ["research", "experiments"]
CATEGORY_LABELS = {
    "research": "Research",
    "experiments": "Experiments",
}
# Directories to skip entirely
SKIP_DIRS = {"raw", "_synthesis", "_archive"}


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse YAML frontmatter from markdown. Returns (metadata, body)."""
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            front = text[3:end].strip()
            body = text[end + 3:].strip()
            meta: dict[str, str] = {}
            for line in front.splitlines():
                if ":" in line:
                    key, _, val = line.partition(":")
                    meta[key.strip()] = val.strip()
            return meta, body
    return {}, text


def _extract_title(path: Path, body: str) -> str:
    """Extract title from first # heading, falling back to filename."""
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


def _collect_notes(notes_dir: Path) -> list[dict[str, str]]:
    """Collect all notes with metadata, excluding meta files and raw/."""
    notes = []
    for path in sorted(notes_dir.rglob("*.md")):
        # Skip meta files, index itself, and notes.md
        if path.name.startswith("_") or path.name in ("notes.md", "index.md"):
            continue

        # Skip directories we don't index
        rel = path.relative_to(notes_dir)
        parts = rel.parts
        if parts and parts[0] in SKIP_DIRS:
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        meta, body = _parse_frontmatter(text)
        title = _extract_title(path, body)

        # Determine category from top-level directory
        if len(parts) > 1:
            category = parts[0]
        else:
            category = "other"

        notes.append({
            "path": str(rel),
            "title": title,
            "creator": meta.get("creator", ""),
            "created": meta.get("created", ""),
            "category": category,
        })
    return notes


def generate_index(notes_dir: Path) -> str:
    """Generate the index content as a string."""
    notes = _collect_notes(notes_dir)

    # Group by category
    groups: dict[str, list[dict[str, str]]] = {}
    for note in notes:
        cat = note["category"]
        groups.setdefault(cat, []).append(note)

    lines = [
        "# Notes Index",
        "",
        f"_Auto-generated. {len(notes)} notes indexed._",
        "",
    ]

    # Known categories first in order, then any unknown categories
    seen = set()
    ordered_cats = []
    for cat in CATEGORY_ORDER:
        if cat in groups:
            ordered_cats.append(cat)
            seen.add(cat)
    for cat in sorted(groups.keys()):
        if cat not in seen:
            ordered_cats.append(cat)

    for cat in ordered_cats:
        cat_notes = groups[cat]
        label = CATEGORY_LABELS.get(cat, cat.title())
        lines.append(f"## {label}")
        lines.append("")

        for note in cat_notes:
            entry = f"- [{note['title']}]({note['path']})"
            detail_parts = []
            if note["creator"]:
                detail_parts.append(note["creator"])
            if note["created"]:
                date = note["created"].split("T")[0] if "T" in note["created"] else note["created"]
                detail_parts.append(date)
            if detail_parts:
                entry += f" — {', '.join(detail_parts)}"
            lines.append(entry)

        lines.append("")

    return "\n".join(lines)


def write_index(notes_dir: Path, dry_run: bool = False) -> str:
    """Generate and write index.md. Returns the content."""
    content = generate_index(notes_dir)

    if dry_run:
        print(content)
        print(f"\n[dry-run] Would write to {notes_dir / 'index.md'}")
        return content

    index_path = notes_dir / "index.md"

    # Atomic write: write to temp file in same directory, then replace
    fd, tmp_path = tempfile.mkstemp(
        dir=str(notes_dir), prefix="_index_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(index_path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    print(f"Wrote {index_path} ({len(content)} bytes)")
    return content


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate index.md for notes directory")
    parser.add_argument("notes_dir", nargs="?", default=".coral/public/notes",
                        help="Path to notes directory (default: .coral/public/notes)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print index to stdout without writing")
    args = parser.parse_args()

    notes_dir = Path(args.notes_dir).resolve()
    if not notes_dir.is_dir():
        print(f"Error: directory not found: {notes_dir}")
        raise SystemExit(1)

    write_index(notes_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
