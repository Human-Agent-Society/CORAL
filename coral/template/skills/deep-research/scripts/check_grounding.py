#!/usr/bin/env python3
"""check_grounding.py — Verify research notes are grounded in saved sources.

Usage:
    python check_grounding.py [NOTES_DIR ...] [--strict] [--quiet] [--json]

The deep-research skill says every finding must trace to a raw source you
actually saved. This script mechanizes that check *offline* — it reads only
files already on disk (no network), so it respects CORAL's rule that web I/O
goes through the runtime's native WebFetch, not a script.

What it checks:
- **orphan-finding** — a `research/*.md` note that links to no `raw/` source
  at all. A synthesis with nothing under it is a claim, not a finding.
- **broken-source-link** — a `[...](.../raw/x.md)` whose target is missing on
  disk (link rot inside the notes base).
- **missing-source-frontmatter** — a `raw/*.md` source lacking a URL, a type,
  and a capture timestamp (accepts either the `source_url/source_type/captured`
  or the older `url/type/fetched` field names).
- **unreviewed-high-confidence** — a note with `confidence: high` but no
  sibling `<slug>.review.json` from the synthesis-reviewer soft gate.
- **uncited-claim** (advisory only) — a line stating a number / % / comparison
  with no citation link on it. Heuristic: noisy by design, never fails --strict.

Defaults to `.coral/public/notes` if no path is given (pass an explicit dir in
multi-island runs, e.g. `.coral/islands/0/notes`).

Advisory by default — exits 0 even with findings. `--strict` exits 1 when any
*hard* finding is present (everything except the heuristic uncited-claim).
`--json` prints a machine-readable report (used by the ablation harness).

Self-contained: no imports from coral.* and stdlib-only, so it ships intact
inside .coral/public/skills/deep-research/scripts/ and runs on a bare
interpreter on every island.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_NOTES_DIR = ".coral/public/notes"

# Findings that indicate a real grounding hole (fail --strict). The heuristic
# uncited-claim is deliberately excluded — it is advisory signal, not a gate.
HARD_CATEGORIES = {
    "orphan-finding",
    "broken-source-link",
    "missing-source-frontmatter",
    "unreviewed-high-confidence",
}

# A raw source must carry a URL, a type, and a capture time. Accept both the
# canonical names (source-types.md) and the older ones (deep-researcher.md),
# so the check is robust to either convention an agent may have used.
URL_FIELDS = ("source_url", "url")
TYPE_FIELDS = ("source_type", "type")
CAPTURED_FIELDS = ("captured", "fetched")

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_WIKILINK_RE = re.compile(r"\[\[[^\]]+\]\]")
# A line "makes a quantitative claim" if it has a bare percentage, a number
# with a unit/multiplier, or a comparative verb sitting next to a number.
_PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s*%")
_NUM_UNIT_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:x|×|fold|ms|s|GB|MB|K|M|B|params|epochs|cycles|AUC)\b")
_COMPARATIVE_RE = re.compile(
    r"\b(?:reduc|improv|outperform|beat|achiev|speedup|faster|slower|higher|lower|"
    r"increase|decrease|better|worse)\w*\b",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\d")


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML-ish frontmatter. Yaml-free for portability (the bundled
    skill must run in a venv that may not have PyYAML)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    front = text[3:end].strip()
    body = text[end + 3 :].strip()
    meta: dict[str, Any] = {}
    for raw in front.splitlines():
        line = raw.rstrip()
        if not line or line.startswith((" ", "\t")) or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        meta[key] = val
    return meta, body


def _first_present(meta: dict[str, Any], keys: tuple[str, ...]) -> str:
    for k in keys:
        v = str(meta.get(k, "") or "").strip()
        if v:
            return v
    return ""


def _iter_md(root: Path) -> list[Path]:
    out: list[Path] = []
    if not root.is_dir():
        return out
    for base, dirs, names in os.walk(root):
        dirs.sort()
        for name in sorted(names):
            if name.endswith(".md"):
                out.append(Path(base) / name)
    return out


def _research_notes(notes_root: Path) -> list[Path]:
    """User research notes: research/**/*.md, excluding `_`-prefixed meta
    files like _coverage.md (they are ledgers, not findings)."""
    return [p for p in _iter_md(notes_root / "research") if not p.name.startswith("_")]


def _raw_sources(notes_root: Path) -> list[Path]:
    return _iter_md(notes_root / "raw")


def _raw_links(note: Path, notes_root: Path) -> tuple[list[str], list[str]]:
    """Return (raw_targets, broken_targets) for links from a note into raw/."""
    raw_dir = (notes_root / "raw").resolve()
    try:
        text = note.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], []
    raw_targets: list[str] = []
    broken: list[str] = []
    for target in _LINK_RE.findall(text):
        clean = target.split("#", 1)[0].split(" ", 1)[0].strip()
        if not clean or "://" in clean:
            continue  # external URL, not a local source link
        resolved = (note.parent / clean).resolve()
        points_to_raw = "raw/" in clean.replace("\\", "/") or str(resolved).startswith(
            str(raw_dir)
        )
        if not points_to_raw:
            continue
        raw_targets.append(clean)
        if not resolved.exists():
            broken.append(clean)
    return raw_targets, broken


def _uncited_claim_lines(note: Path) -> list[int]:
    """Line numbers of quantitative claims with no citation on the line (or the
    next one). Heuristic — advisory only."""
    try:
        lines = note.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    flagged: list[int] = []
    in_code = False
    in_front = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if i == 0 and stripped == "---":
            in_front = True
            continue
        if in_front:
            if stripped == "---":
                in_front = False
            continue
        if in_code or not stripped or stripped.startswith(("#", "|", ">")):
            continue
        is_claim = bool(_PERCENT_RE.search(line) or _NUM_UNIT_RE.search(line)) or bool(
            _COMPARATIVE_RE.search(line) and _NUMBER_RE.search(line)
        )
        if not is_claim:
            continue
        window = line + (lines[i + 1] if i + 1 < len(lines) else "")
        cited = "](" in window or _WIKILINK_RE.search(window) or "raw/" in window or "^[" in window
        if not cited:
            flagged.append(i + 1)
    return flagged


def check_notes(notes_root: Path) -> dict[str, Any]:
    """Run every grounding check over one notes directory."""
    findings: list[dict[str, str]] = []

    def add(file: Path, category: str, detail: str) -> None:
        findings.append(
            {"file": file.relative_to(notes_root).as_posix(), "category": category, "detail": detail}
        )

    research = _research_notes(notes_root)
    raw = _raw_sources(notes_root)

    for note in research:
        raw_targets, broken = _raw_links(note, notes_root)
        if not raw_targets:
            add(note, "orphan-finding", "no link to any raw/ source — finding is ungrounded")
        for b in broken:
            add(note, "broken-source-link", f"links to `{b}` which does not exist on disk")
        meta, _ = _parse_frontmatter(note.read_text(encoding="utf-8", errors="replace"))
        if str(meta.get("confidence", "")).strip().lower() == "high":
            review = note.with_suffix(".review.json")
            if not review.exists():
                add(
                    note,
                    "unreviewed-high-confidence",
                    "confidence: high but no sibling <slug>.review.json (synthesis-reviewer soft gate)",
                )
        for ln in _uncited_claim_lines(note):
            add(note, "uncited-claim", f"line {ln}: quantitative claim with no citation link")

    for src in raw:
        meta, _ = _parse_frontmatter(src.read_text(encoding="utf-8", errors="replace"))
        missing = []
        if not _first_present(meta, URL_FIELDS):
            missing.append("source_url")
        if not _first_present(meta, TYPE_FIELDS):
            missing.append("source_type")
        if not _first_present(meta, CAPTURED_FIELDS):
            missing.append("captured")
        if missing:
            add(src, "missing-source-frontmatter", f"raw source missing {', '.join(missing)}")

    summary: dict[str, Any] = {c: 0 for c in sorted(HARD_CATEGORIES | {"uncited-claim"})}
    for f in findings:
        summary[f["category"]] += 1
    summary["total"] = len(findings)
    # A rough 0..1 cleanliness proxy for the ablation. Hard findings cost 1,
    # the heuristic uncited-claim costs 0.25, normalized by opportunities.
    opportunities = max(1, len(research) + len(raw))
    weighted = sum(
        1.0 if f["category"] in HARD_CATEGORIES else 0.25 for f in findings
    )
    summary["research_notes"] = len(research)
    summary["raw_sources"] = len(raw)
    summary["grounding_score"] = round(max(0.0, 1.0 - weighted / opportunities), 3)

    return {"notes_dir": str(notes_root), "findings": findings, "summary": summary}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("paths", nargs="*", help="Notes directory (default: .coral/public/notes)")
    ap.add_argument("--strict", action="store_true", help="Exit 1 if any hard finding")
    ap.add_argument("--quiet", action="store_true", help="Only print files with findings")
    ap.add_argument("--json", action="store_true", help="Emit a JSON report")
    args = ap.parse_args()

    roots = [Path(p) for p in (args.paths or [DEFAULT_NOTES_DIR])]
    reports = []
    hard_total = 0
    for root in roots:
        if not root.is_dir():
            print(f"warning: {root} is not a directory", file=sys.stderr)
            continue
        report = check_notes(root)
        reports.append(report)
        hard_total += sum(
            report["summary"][c] for c in HARD_CATEGORIES
        )

    if args.json:
        print(json.dumps(reports if len(reports) != 1 else reports[0], indent=2))
        return 1 if (args.strict and hard_total) else 0

    for report in reports:
        by_file: dict[str, list[dict[str, str]]] = {}
        for f in report["findings"]:
            by_file.setdefault(f["file"], []).append(f)
        s = report["summary"]
        print(f"\n# {report['notes_dir']}")
        for file in sorted(by_file):
            print(f"\n{file}")
            for f in by_file[file]:
                print(f"  - [{f['category']}] {f['detail']}")
        if not by_file and not args.quiet:
            print("  ok — no grounding findings")
        print(
            f"\n{s['research_notes']} research note(s), {s['raw_sources']} raw source(s); "
            f"{s['total']} finding(s) "
            f"(orphan={s['orphan-finding']}, broken={s['broken-source-link']}, "
            f"missing-frontmatter={s['missing-source-frontmatter']}, "
            f"unreviewed-high-conf={s['unreviewed-high-confidence']}, "
            f"uncited={s['uncited-claim']}); grounding_score={s['grounding_score']}"
        )

    return 1 if (args.strict and hard_total) else 0


if __name__ == "__main__":
    sys.exit(main())
