#!/usr/bin/env python3
"""resolve_links.py — Wikilink resolver for the notes directory.

Two passes inspired by llmwiki's resolver (compiler/resolver.ts):

  1. Outbound: for every note, scan its body for plain-text mentions of
     other notes' titles and wrap them as [[slug|Title]] wikilinks.

  2. Inbound (--new flag): when given a list of newly added/renamed slugs,
     scan EVERY note for mentions of those titles and link them. This is the
     pass that fixes "old notes never get re-linked when a new note lands".

Skips:
  - text already inside [[ ]] wikilinks
  - text inside ^[ ] citation markers
  - text inside fenced code blocks (``` ... ```) and inline code (` ... `)
  - the note's own title (no self-links)
  - frontmatter (only the body is mutated)

Title source: the YAML `title:` field of each note's frontmatter. Notes
without a title are silently ignored.

Excluded directories: raw/, _archive/, _synthesis/, and anything else
matching --exclude.

Usage:
  python resolve_links.py NOTES_DIR              # outbound pass on all notes
  python resolve_links.py NOTES_DIR --dry-run    # show diffs, write nothing
  python resolve_links.py NOTES_DIR --new slug1,slug2   # also do inbound for these slugs

Exit code 0 always (no error if no changes).
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

EXCLUDED_DIRS_DEFAULT = {"raw", "_archive", "_synthesis"}
FRONTMATTER_DELIMITER = "---"
WORD_BOUNDARY_CHARS = set(" \t\n,.:;!?()[]{}/\"'")


@dataclass
class Note:
    path: Path
    slug: str
    title: str
    frontmatter: str  # raw frontmatter block, including delimiters
    body: str


def load_notes(root: Path, excluded_dirs: set[str]) -> list[Note]:
    """Walk root, return every .md file with a frontmatter title."""
    notes: list[Note] = []
    for md_path in root.rglob("*.md"):
        if any(part in excluded_dirs for part in md_path.relative_to(root).parts):
            continue
        if md_path.name.startswith("_"):
            continue  # skip _organization-log.md, _open-questions.md, etc.
        note = parse_note(md_path)
        if note is not None:
            notes.append(note)
    return notes


def parse_note(path: Path) -> Note | None:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith(FRONTMATTER_DELIMITER):
        return None
    parts = raw.split(FRONTMATTER_DELIMITER + "\n", 2)
    if len(parts) < 3:
        return None
    _, frontmatter_body, body = parts
    title = extract_title(frontmatter_body)
    if not title:
        return None
    frontmatter = f"{FRONTMATTER_DELIMITER}\n{frontmatter_body}{FRONTMATTER_DELIMITER}\n"
    slug = path.stem
    return Note(path=path, slug=slug, title=title, frontmatter=frontmatter, body=body)


def extract_title(frontmatter_body: str) -> str | None:
    """Pull the title field from a YAML frontmatter block.

    Tolerates `title: foo`, `title: "foo"`, `title: 'foo'`, with optional
    leading whitespace. Doesn't pull in a full YAML parser to keep the
    script dependency-free.
    """
    for line in frontmatter_body.splitlines():
        match = re.match(r'^\s*title:\s*(.+?)\s*$', line)
        if match:
            value = match.group(1).strip()
            # Strip surrounding quotes if present.
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            return value or None
    return None


def find_protected_spans(text: str) -> list[tuple[int, int]]:
    """Identify [start, end) ranges in text that must not be modified.

    Covers existing [[...]], ^[...], inline `code`, and fenced ``` blocks.
    Returned spans may overlap; that's fine — the caller treats any
    position inside ANY span as protected.
    """
    spans: list[tuple[int, int]] = []
    spans.extend(_find_pattern_spans(text, r"\[\[[^\]]*\]\]"))
    spans.extend(_find_pattern_spans(text, r"\^\[[^\]]*\]"))
    spans.extend(_find_pattern_spans(text, r"`[^`\n]+`"))
    spans.extend(_find_pattern_spans(text, r"```.*?```", re.DOTALL))
    return spans


def _find_pattern_spans(text: str, pattern: str, flags: int = 0) -> Iterable[tuple[int, int]]:
    for match in re.finditer(pattern, text, flags):
        yield (match.start(), match.end())


def is_protected(position: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in spans)


def is_word_boundary(text: str, start: int, end: int) -> bool:
    before_ok = start == 0 or text[start - 1] in WORD_BOUNDARY_CHARS
    after_ok = end >= len(text) or text[end] in WORD_BOUNDARY_CHARS
    return before_ok and after_ok


def add_wikilinks(body: str, candidates: list[Note], self_title: str) -> str:
    """Wrap plain mentions of each candidate's title as [[slug|Title]].

    Processes longer titles first so "Flash Attention" wins over "Attention"
    when both appear in the candidate set.
    """
    self_lower = self_title.lower()
    sorted_candidates = sorted(candidates, key=lambda n: -len(n.title))
    result = body
    for candidate in sorted_candidates:
        if candidate.title.lower() == self_lower:
            continue
        result = _link_one_title(result, candidate.title, candidate.slug)
    return result


def _link_one_title(text: str, title: str, slug: str) -> str:
    # Re-compute protected spans on each pass — the previous pass may have
    # introduced new [[...]] spans we now need to skip.
    protected = find_protected_spans(text)
    pattern = re.compile(re.escape(title), re.IGNORECASE)
    # Walk matches in reverse so earlier indices stay valid as we edit.
    matches = list(pattern.finditer(text))
    for match in reversed(matches):
        start, end = match.start(), match.end()
        if is_protected(start, protected):
            continue
        if not is_word_boundary(text, start, end):
            continue
        replacement = f"[[{slug}|{text[start:end]}]]"
        text = text[:start] + replacement + text[end:]
    return text


def write_note_if_changed(note: Note, new_body: str, dry_run: bool) -> bool:
    if new_body == note.body:
        return False
    if dry_run:
        print(f"--- would update: {note.path}")
        _print_body_diff(note.body, new_body)
    else:
        note.path.write_text(note.frontmatter + new_body, encoding="utf-8")
        print(f"updated: {note.path}")
    return True


def _print_body_diff(old: str, new: str) -> None:
    """Print a tiny line-level summary of additions; full diff is overkill."""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    changed = 0
    for old_line, new_line in zip(old_lines, new_lines):
        if old_line != new_line:
            print(f"  - {old_line.strip()[:120]}")
            print(f"  + {new_line.strip()[:120]}")
            changed += 1
            if changed >= 5:
                print("  (... more changes elided)")
                break


def run_outbound(notes: list[Note], dry_run: bool) -> int:
    changed_count = 0
    for note in notes:
        new_body = add_wikilinks(note.body, notes, note.title)
        if write_note_if_changed(note, new_body, dry_run):
            changed_count += 1
    return changed_count


def run_inbound(notes: list[Note], new_slugs: set[str], dry_run: bool) -> int:
    new_notes = [n for n in notes if n.slug in new_slugs]
    if not new_notes:
        print(f"no notes match --new slugs: {sorted(new_slugs)}", file=sys.stderr)
        return 0
    changed_count = 0
    # Skip notes that were the *target* of new (already linked outbound above).
    targets = [n for n in notes if n.slug not in new_slugs]
    for note in targets:
        new_body = add_wikilinks(note.body, new_notes, note.title)
        if write_note_if_changed(note, new_body, dry_run):
            changed_count += 1
    return changed_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("notes_dir", type=Path, help="root of the notes/ directory")
    parser.add_argument("--dry-run", action="store_true", help="print diffs, write nothing")
    parser.add_argument("--new", type=str, default="", help="comma-separated slugs to also do an inbound pass for")
    parser.add_argument("--exclude", type=str, default="", help="comma-separated extra dir names to exclude")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.notes_dir.is_dir():
        print(f"not a directory: {args.notes_dir}", file=sys.stderr)
        return 1

    excluded = set(EXCLUDED_DIRS_DEFAULT)
    if args.exclude:
        excluded.update(p.strip() for p in args.exclude.split(",") if p.strip())

    notes = load_notes(args.notes_dir, excluded)
    if not notes:
        print("no notes with a frontmatter title found", file=sys.stderr)
        return 0

    print(f"loaded {len(notes)} notes from {args.notes_dir}")
    outbound_changes = run_outbound(notes, args.dry_run)
    print(f"outbound pass: {outbound_changes} note(s) {'would change' if args.dry_run else 'updated'}")

    if args.new:
        new_slugs = {s.strip() for s in args.new.split(",") if s.strip()}
        # Reload notes so the inbound pass sees outbound-pass edits.
        if not args.dry_run:
            notes = load_notes(args.notes_dir, excluded)
        inbound_changes = run_inbound(notes, new_slugs, args.dry_run)
        print(f"inbound pass: {inbound_changes} note(s) {'would change' if args.dry_run else 'updated'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
