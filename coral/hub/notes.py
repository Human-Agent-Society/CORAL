"""Read/list/search notes from .coral/public/notes/ directory.

Notes are individual Markdown files with optional YAML frontmatter:

    ---
    creator: agent-1
    created: 2026-03-14T17:35:00-00:00
    ---
    # Title of the note
    Body text with findings, numbers, conclusions...

Legacy format (single notes.md with ## headings) is also supported.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _notes_dir(coral_dir: str | Path) -> Path:
    """Return the path to the notes directory, ensuring it exists."""
    p = Path(coral_dir) / "public" / "notes"
    p.mkdir(parents=True, exist_ok=True)
    return p


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


def _parse_legacy_entries(text: str) -> list[dict[str, Any]]:
    """Parse legacy notes.md (## [date] title format) into entries."""
    pattern = re.compile(r"^## ", re.MULTILINE)
    parts = pattern.split(text)
    entries = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.match(r"\[([^\]]*)\]\s*(.*)", part, re.DOTALL)
        if m:
            date = m.group(1).strip()
            rest = m.group(2)
            title_line, _, body = rest.partition("\n")
            title = title_line.strip()
            body = body.strip()
        else:
            title_line, _, body = part.partition("\n")
            date = ""
            title = title_line.strip()
            body = body.strip()

        entries.append({
            "date": date,
            "title": title,
            "body": body,
            "creator": "",
            "filename": "notes.md",
        })
    return entries


def _parse_note_file(path: Path) -> dict[str, Any]:
    """Parse a single note .md file into an entry dict."""
    text = path.read_text()
    meta, body = _parse_frontmatter(text)

    # Extract title from first # heading
    title = path.stem.replace("-", " ").replace("_", " ").title()
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# "):
            title = line[2:].strip()
            break

    return {
        "date": meta.get("created", ""),
        "title": title,
        "body": body,
        "creator": meta.get("creator", ""),
        "filename": path.name,
        "_mtime": os.path.getmtime(path),
    }


def _collect_from_dir(directory: Path) -> list[dict[str, Any]]:
    """Collect note entries from a single directory."""
    if not directory.is_dir():
        return []

    md_files = sorted(
        f for f in directory.glob("*.md") if f.name != "notes.md"
    )

    if md_files:
        entries = [_parse_note_file(f) for f in md_files]
        legacy = directory / "notes.md"
        if legacy.exists() and legacy.stat().st_size > 0:
            entries.extend(_parse_legacy_entries(legacy.read_text()))
        return entries

    legacy = directory / "notes.md"
    if legacy.exists() and legacy.stat().st_size > 0:
        return _parse_legacy_entries(legacy.read_text())

    return []


def _sort_key(entry: dict[str, Any]) -> datetime:
    """Return a datetime for sorting. Parses the frontmatter date string,
    falling back to file mtime if unavailable or unparseable."""
    date_str = entry.get("date", "")
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except (ValueError, TypeError):
            pass
    mtime = entry.get("_mtime")
    if mtime is not None:
        return datetime.fromtimestamp(mtime, tz=UTC)
    return datetime.min.replace(tzinfo=UTC)


def list_notes(coral_dir: str | Path) -> list[dict[str, Any]]:
    """List all note entries from the notes directory.

    Reads individual .md files. Falls back to legacy notes.md format.
    Also checks the legacy 'insights/' directory for backward compatibility.
    """
    notes_dir = _notes_dir(coral_dir)
    entries = _collect_from_dir(notes_dir)

    # Also read from insights/ directory if present
    insights_dir = Path(coral_dir) / "public" / "insights"
    if insights_dir.is_dir():
        seen = {e["filename"] for e in entries}
        for e in _collect_from_dir(insights_dir):
            if e["filename"] not in seen:
                entries.append(e)

    entries.sort(key=_sort_key)
    return entries


def search_notes(coral_dir: str | Path, query: str) -> list[dict[str, Any]]:
    """Search notes by keyword (case-insensitive) in title and body."""
    query_lower = query.lower()
    results = []
    for entry in list_notes(coral_dir):
        full_text = f"{entry['title']} {entry['body']}".lower()
        if query_lower in full_text:
            results.append(entry)
    return results


def get_recent_notes(coral_dir: str | Path, n: int = 5) -> list[dict[str, Any]]:
    """Return the last N notes (most recent last in file = most recent last)."""
    entries = list_notes(coral_dir)
    return entries[-n:] if len(entries) > n else entries


def format_notes_list(entries: list[dict[str, Any]]) -> str:
    """Format note entries for terminal display."""
    if not entries:
        return "No notes yet."
    lines = []
    for i, e in enumerate(entries, 1):
        date_str = f"[{e['date']}] " if e.get("date") else ""
        creator_str = f" ({e['creator']})" if e.get("creator") else ""
        lines.append(f"  {i}. {date_str}{e['title']}{creator_str}")
    return "\n".join(lines)


def read_note(coral_dir: str | Path, index: int) -> str | None:
    """Read a specific note entry by index (1-based)."""
    entries = list_notes(coral_dir)
    if 1 <= index <= len(entries):
        e = entries[index - 1]
        return e["body"]
    return None


def read_all_notes(coral_dir: str | Path) -> str:
    """Read all notes concatenated."""
    entries = list_notes(coral_dir)
    if not entries:
        return ""
    parts = []
    for e in entries:
        parts.append(e["body"])
    return "\n\n---\n\n".join(parts)
