"""The deep-research grounding lint must catch ungrounded findings.

`check_grounding.py` is the mechanical enforcement of the skill's "retrieve
first, then write" rule. This test pins its detections (orphan findings, broken
raw links, missing source frontmatter, unreviewed high-confidence notes) and its
--strict exit behavior, so future edits to the script don't silently stop
flagging ungrounded research.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

SCRIPT = Path("coral/template/skills/deep-research/scripts/check_grounding.py")


def _load_script(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _dirty_notes(root: Path) -> Path:
    """A notes/ tree containing exactly one of each grounding problem plus one
    clean note, and a `_coverage.md` ledger that must NOT be linted as a note."""
    notes = root / "notes"
    # clean research note: cites an existing, well-formed raw source
    _write(
        notes / "research" / "good.md",
        "---\ncreator: a\nconfidence: low\n---\n# Good\n"
        "Method Y cuts cost (see [src](../raw/good-src.md)).\n",
    )
    _write(
        notes / "raw" / "good-src.md",
        "---\nsource_url: http://example.com\nsource_type: paper\ncaptured: 2026-01-01\n---\nbody\n",
    )
    # orphan finding: no raw link at all
    _write(notes / "research" / "orphan.md", "---\ncreator: a\n---\n# Orphan\nNo sources here.\n")
    # broken source link: target does not exist
    _write(
        notes / "research" / "broken.md",
        "---\ncreator: a\n---\n# Broken\nClaim (see [x](../raw/missing.md)).\n",
    )
    # unreviewed high-confidence note (cites a real source, but no .review.json)
    _write(
        notes / "research" / "hot.md",
        "---\ncreator: a\nconfidence: high\n---\n# Hot\nBig claim [s](../raw/good-src.md).\n",
    )
    # raw source missing required frontmatter
    _write(notes / "raw" / "bad-src.md", "---\ntitle: nope\n---\nbody\n")
    # coverage ledger — a meta file, must be ignored by the note checks
    _write(
        notes / "research" / "_coverage.md",
        "# Research Coverage\n| Dim | Status |\n|-----|--------|\n| Prior art | missing |\n",
    )
    return notes


def test_check_notes_flags_each_problem(tmp_path):
    mod = _load_script(SCRIPT)
    notes = _dirty_notes(tmp_path)

    report = mod.check_notes(notes)
    summary = report["summary"]
    cats = {f["category"] for f in report["findings"]}

    assert summary["orphan-finding"] == 1
    assert summary["broken-source-link"] == 1
    assert summary["missing-source-frontmatter"] == 1
    assert summary["unreviewed-high-confidence"] == 1
    assert {"orphan-finding", "broken-source-link", "missing-source-frontmatter",
            "unreviewed-high-confidence"} <= cats

    # _coverage.md is a meta file: it must not be counted as a research note and
    # must never itself be flagged as an orphan finding.
    flagged_files = {f["file"] for f in report["findings"]}
    assert "research/_coverage.md" not in flagged_files
    # good.md is fully grounded → it produces no findings
    assert "research/good.md" not in flagged_files


def test_clean_tree_has_no_hard_findings(tmp_path):
    mod = _load_script(SCRIPT)
    notes = tmp_path / "notes"
    _write(
        notes / "research" / "good.md",
        "---\ncreator: a\nconfidence: low\n---\n# Good\nClaim [s](../raw/s.md).\n",
    )
    _write(
        notes / "raw" / "s.md",
        "---\nsource_url: http://e.com\nsource_type: paper\ncaptured: 2026-01-01\n---\nx\n",
    )
    report = mod.check_notes(notes)
    hard = sum(report["summary"][c] for c in mod.HARD_CATEGORIES)
    assert hard == 0
    assert report["summary"]["grounding_score"] == 1.0


def test_strict_exit_codes(tmp_path):
    notes = _dirty_notes(tmp_path)
    dirty = subprocess.run(
        [sys.executable, str(SCRIPT), str(notes), "--strict"],
        capture_output=True,
        text=True,
    )
    assert dirty.returncode == 1, dirty.stdout + dirty.stderr

    clean_root = tmp_path / "clean"
    _write(
        clean_root / "notes" / "research" / "good.md",
        "---\ncreator: a\n---\n# Good\nClaim [s](../raw/s.md).\n",
    )
    _write(
        clean_root / "notes" / "raw" / "s.md",
        "---\nsource_url: http://e.com\nsource_type: repo\ncaptured: 2026-01-01\n---\nx\n",
    )
    clean = subprocess.run(
        [sys.executable, str(SCRIPT), str(clean_root / "notes"), "--strict"],
        capture_output=True,
        text=True,
    )
    assert clean.returncode == 0, clean.stdout + clean.stderr
