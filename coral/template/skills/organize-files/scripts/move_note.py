#!/usr/bin/env python3
"""move_note.py — Safely move/rename a note with frontmatter tracking.

Usage: python move_note.py SOURCE DEST [--force] [--dry-run]

Safety features:
- Refuses files modified <5 minutes ago (override with --force)
- Write-first-delete-second (verifies write before removing source)
- Auto-adds moved_from/renamed_from/moved_at to frontmatter
- Creates parent directories automatically

Self-contained — no imports from coral.hub.
"""

import argparse
import os
from datetime import datetime, timezone
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


def _serialize_frontmatter(meta: dict[str, str], body: str) -> str:
    """Serialize metadata and body back to markdown with frontmatter."""
    lines = ["---"]
    for key, val in meta.items():
        lines.append(f"{key}: {val}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    return "\n".join(lines)


def _file_age_minutes(path: Path) -> float:
    """Return the age of a file in minutes based on mtime."""
    mtime = os.path.getmtime(path)
    now = datetime.now(timezone.utc).timestamp()  # noqa: UP017
    return (now - mtime) / 60.0


def _is_rename(source: Path, dest: Path) -> bool:
    """Check if this is a rename (same directory) vs a move."""
    return source.parent.resolve() == dest.parent.resolve()


def move_note(source: Path, dest: Path, force: bool = False, dry_run: bool = False) -> None:
    """Move a note file from source to dest with safety checks and tracking."""
    # Validate source
    if not source.exists():
        print(f"Error: source not found: {source}")
        raise SystemExit(1)

    if not source.is_file():
        print(f"Error: source is not a file: {source}")
        raise SystemExit(1)

    if not source.suffix == ".md":
        print(f"Warning: source is not a .md file: {source}")

    # Check dest
    if dest.exists() and not force:
        print(f"Error: destination already exists: {dest}")
        print("Use --force to overwrite.")
        raise SystemExit(1)

    # Safety: refuse files modified less than 5 minutes ago
    age = _file_age_minutes(source)
    if age < 5.0 and not force:
        print(f"Error: {source.name} was modified {age:.1f} minutes ago (< 5 min).")
        print("Another agent may be writing to it. Use --force to override.")
        raise SystemExit(1)

    # Read and update content
    text = source.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)

    # Add tracking metadata
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")  # noqa: UP017
    if _is_rename(source, dest):
        meta["renamed_from"] = source.name
    else:
        meta["moved_from"] = str(source)
    meta["moved_at"] = now

    new_content = _serialize_frontmatter(meta, body)

    if dry_run:
        action = "Rename" if _is_rename(source, dest) else "Move"
        print(f"[dry-run] {action}: {source} -> {dest}")
        print("[dry-run] Would add to frontmatter:")
        if _is_rename(source, dest):
            print(f"  renamed_from: {source.name}")
        else:
            print(f"  moved_from: {source}")
        print(f"  moved_at: {now}")
        return

    # Create parent directories
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Write-first-delete-second: write to destination, verify, then remove source
    dest.write_text(new_content, encoding="utf-8")

    # Verify the write succeeded
    if not dest.exists() or dest.stat().st_size == 0:
        print(f"Error: write verification failed for {dest}")
        raise SystemExit(1)

    # Verify content matches
    written = dest.read_text(encoding="utf-8")
    if written != new_content:
        print(f"Error: content verification failed for {dest}")
        raise SystemExit(1)

    # Safe to delete source now
    source.unlink()

    action = "Renamed" if _is_rename(source, dest) else "Moved"
    print(f"{action}: {source} -> {dest}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely move/rename a note with frontmatter tracking")
    parser.add_argument("source", type=Path, help="Source note file")
    parser.add_argument("dest", type=Path, help="Destination path")
    parser.add_argument("--force", action="store_true",
                        help="Override safety checks (age limit, existing dest)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without making changes")
    args = parser.parse_args()

    move_note(args.source.resolve(), args.dest.resolve(), force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
