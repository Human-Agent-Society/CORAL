#!/usr/bin/env python3
"""generate_index.py — Auto-generate _index.md for a notes directory.

Usage: python generate_index.py [NOTES_DIR] [--dry-run]
Defaults to .coral/public/notes if no argument given.

Produces a navigable table of contents grouped by directory, showing
title, creator, and date per note. Uses atomic writes (write to temp
file, then os.replace) for safe concurrent access.

Idempotent — same input produces same output.
Self-contained — no imports from coral.hub.
"""

import argparse
import os
import tempfile
from pathlib import Path


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
    """Collect all notes with metadata, excluding meta files."""
    notes = []
    for path in sorted(notes_dir.rglob("*.md")):
        # Skip meta files and the index itself
        if path.name.startswith("_") or path.name == "notes.md":
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        meta, body = _parse_frontmatter(text)
        title = _extract_title(path, body)
        rel_path = path.relative_to(notes_dir)

        notes.append({
            "path": str(rel_path),
            "title": title,
            "creator": meta.get("creator", ""),
            "created": meta.get("created", ""),
        })
    return notes


def _group_by_directory(notes: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Group notes by their parent directory."""
    groups: dict[str, list[dict[str, str]]] = {}
    for note in notes:
        parent = str(Path(note["path"]).parent)
        if parent == ".":
            parent = "(top-level)"
        groups.setdefault(parent, []).append(note)
    return groups


def generate_index(notes_dir: Path) -> str:
    """Generate the index content as a string."""
    notes = _collect_notes(notes_dir)
    groups = _group_by_directory(notes)

    lines = [
        "# Notes Index",
        "",
        f"_Auto-generated. {len(notes)} notes indexed._",
        "",
    ]

    # Sort groups: top-level first, then alphabetical
    sorted_groups = sorted(groups.keys(), key=lambda k: ("" if k == "(top-level)" else k))

    for group in sorted_groups:
        group_notes = groups[group]
        lines.append(f"## {group}")
        lines.append("")

        for note in group_notes:
            parts = [f"- **{note['title']}**"]
            detail_parts = []
            if note["creator"]:
                detail_parts.append(note["creator"])
            if note["created"]:
                # Show just the date part
                date = note["created"].split("T")[0] if "T" in note["created"] else note["created"]
                detail_parts.append(date)
            detail_parts.append(f"`{note['path']}`")

            if detail_parts:
                parts.append(f" — {', '.join(detail_parts)}")
            lines.append("".join(parts))

        lines.append("")

    return "\n".join(lines)


def write_index(notes_dir: Path, dry_run: bool = False) -> str:
    """Generate and write _index.md. Returns the content."""
    content = generate_index(notes_dir)

    if dry_run:
        print(content)
        print(f"\n[dry-run] Would write to {notes_dir / '_index.md'}")
        return content

    index_path = notes_dir / "_index.md"

    # Atomic write: write to temp file in same directory, then replace
    fd, tmp_path = tempfile.mkstemp(
        dir=str(notes_dir), prefix="_index_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(index_path))
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    print(f"Wrote {index_path} ({len(content)} bytes)")
    return content


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate _index.md for notes directory")
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
