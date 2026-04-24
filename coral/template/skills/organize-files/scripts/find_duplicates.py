#!/usr/bin/env python3
"""find_duplicates.py — Find duplicate/near-duplicate notes using Jaccard similarity.

Usage: python find_duplicates.py [NOTES_DIR] [--threshold 0.5] [--json]

Algorithm: Weighted Jaccard similarity on word sets from titles (weight 0.6)
and first paragraphs (weight 0.4). O(n^2) comparison — fine for <200 notes.

This script NEVER modifies any files. Self-contained — no imports from coral.hub.
"""

import argparse
import json
import re
from pathlib import Path

STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "this", "that", "it", "not", "no",
})


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


def _tokenize(text: str) -> set[str]:
    """Extract lowercase word tokens, filtering stop words."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in STOP_WORDS and len(w) > 1}


def _extract_title(path: Path, body: str) -> str:
    """Extract title from first # heading, falling back to filename."""
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ").replace("_", " ")


def _extract_first_paragraph(body: str) -> str:
    """Extract the first non-heading paragraph from the body."""
    lines = []
    found_content = False
    for line in body.splitlines():
        stripped = line.strip()
        # Skip headings and empty lines before content
        if stripped.startswith("#"):
            if found_content:
                break
            continue
        if not stripped:
            if found_content:
                break
            continue
        found_content = True
        lines.append(stripped)
    return " ".join(lines)


def _jaccard(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _weighted_similarity(
    title_a: set[str], title_b: set[str],
    para_a: set[str], para_b: set[str],
    title_weight: float = 0.6,
    para_weight: float = 0.4,
) -> float:
    """Compute weighted Jaccard similarity from title and paragraph tokens."""
    title_sim = _jaccard(title_a, title_b)
    para_sim = _jaccard(para_a, para_b)
    return title_weight * title_sim + para_weight * para_sim


def find_duplicates(
    notes_dir: Path, threshold: float = 0.5
) -> list[dict]:
    """Find duplicate note pairs above the similarity threshold."""
    # Collect notes
    notes = []
    for path in sorted(notes_dir.rglob("*.md")):
        if path.name.startswith("_") or path.name == "notes.md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        _, body = _parse_frontmatter(text)
        title = _extract_title(path, body)
        first_para = _extract_first_paragraph(body)

        notes.append({
            "path": str(path.relative_to(notes_dir)),
            "title": title,
            "title_tokens": _tokenize(title),
            "para_tokens": _tokenize(first_para),
        })

    # Pairwise comparison
    pairs = []
    for i in range(len(notes)):
        for j in range(i + 1, len(notes)):
            sim = _weighted_similarity(
                notes[i]["title_tokens"], notes[j]["title_tokens"],
                notes[i]["para_tokens"], notes[j]["para_tokens"],
            )
            if sim >= threshold:
                pairs.append({
                    "file_a": notes[i]["path"],
                    "title_a": notes[i]["title"],
                    "file_b": notes[j]["path"],
                    "title_b": notes[j]["title"],
                    "similarity": round(sim, 3),
                })

    # Sort by similarity descending
    pairs.sort(key=lambda p: p["similarity"], reverse=True)
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(description="Find duplicate/near-duplicate notes")
    parser.add_argument("notes_dir", nargs="?", default=".coral/public/notes",
                        help="Path to notes directory (default: .coral/public/notes)")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Similarity threshold 0.0-1.0 (default: 0.5)")
    parser.add_argument("--json", action="store_true", dest="json_output",
                        help="Output as JSON")
    args = parser.parse_args()

    notes_dir = Path(args.notes_dir).resolve()
    if not notes_dir.is_dir():
        print(f"Error: directory not found: {notes_dir}")
        raise SystemExit(1)

    pairs = find_duplicates(notes_dir, threshold=args.threshold)

    if args.json_output:
        print(json.dumps(pairs, indent=2))
        return

    if not pairs:
        print("No duplicates found above threshold.")
        return

    print(f"Found {len(pairs)} potential duplicate pair(s):\n")
    for p in pairs:
        print(f"  Similarity: {p['similarity']:.1%}")
        print(f"    A: {p['file_a']}")
        print(f"       \"{p['title_a']}\"")
        print(f"    B: {p['file_b']}")
        print(f"       \"{p['title_b']}\"")
        print()


if __name__ == "__main__":
    main()
