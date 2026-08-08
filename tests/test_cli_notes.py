"""Tests for ``coral notes`` status filtering (issue #200)."""

import argparse
import subprocess
import sys
from pathlib import Path

from coral.cli import query as query_module
from coral.cli.query import cmd_notes
from coral.hub.notes import get_recent_notes, list_notes, search_notes


def _write_note(
    coral_dir: Path,
    name: str,
    status: str | None,
    *,
    created: str = "2026-08-07",
) -> None:
    notes_dir = coral_dir / "public" / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    frontmatter = ["---", "creator: agent-1", f"created: {created}"]
    if status is not None:
        frontmatter.append(f'status: "{status}"')
    frontmatter.extend(["---", "", f"# {name}", "", f"{name} body"])
    (notes_dir / f"{name}.md").write_text("\n".join(frontmatter), encoding="utf-8")


def _run_cmd_notes(
    coral_dir: Path,
    monkeypatch,
    capsys,
    **overrides: object,
) -> str:
    monkeypatch.setattr(
        query_module,
        "find_coral_dir_and_island",
        lambda task=None, run=None: (coral_dir, None),
    )
    options: dict[str, object] = {
        "history": False,
        "diff": None,
        "read": None,
        "search": None,
        "recent": None,
        "status": None,
        "task": None,
        "run": None,
    }
    options.update(overrides)
    cmd_notes(argparse.Namespace(**options))
    return capsys.readouterr().out


def test_list_notes_filters_status_case_insensitively_and_ignores_whitespace(
    tmp_path: Path,
) -> None:
    _write_note(tmp_path, "lower", "confirmed")
    _write_note(tmp_path, "mixed", " Confirmed ")
    _write_note(tmp_path, "prefixed", "confirmed-extra")
    _write_note(tmp_path, "refuted", "refuted")
    _write_note(tmp_path, "missing", None)

    entries = list_notes(tmp_path, status=" CONFIRMED ")

    assert [entry["title"] for entry in entries] == ["lower", "mixed"]


def test_search_notes_composes_with_status_filter(tmp_path: Path) -> None:
    _write_note(tmp_path, "confirmed-tiling", "confirmed")
    _write_note(tmp_path, "refuted-tiling", "refuted")
    _write_note(tmp_path, "confirmed-kernel", "confirmed")

    entries = search_notes(tmp_path, "tiling", status="confirmed")

    assert [entry["title"] for entry in entries] == ["confirmed-tiling"]


def test_list_notes_accepts_future_status_values(tmp_path: Path) -> None:
    _write_note(tmp_path, "future-note", "needs-review")
    _write_note(tmp_path, "confirmed-note", "confirmed")
    _write_note(tmp_path, "legacy-note", None)

    entries = list_notes(tmp_path, status="needs-review")

    assert [entry["title"] for entry in entries] == ["future-note"]


def test_notes_cli_accepts_future_status_values(tmp_path: Path) -> None:
    coral_dir = tmp_path / "coral"
    worktree = tmp_path / "worktree"
    _write_note(coral_dir, "future-note", "needs-review")
    _write_note(coral_dir, "confirmed-note", "confirmed")
    worktree.mkdir()
    (worktree / ".coral_dir").write_text(str(coral_dir), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "coral.cli", "notes", "--status", "needs-review"],
        cwd=worktree,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert "future-note" in result.stdout
    assert "confirmed-note" not in result.stdout


def test_recent_notes_filters_before_returning_latest_count(tmp_path: Path) -> None:
    _write_note(tmp_path, "confirmed-old", "confirmed", created="2026-08-01")
    _write_note(tmp_path, "confirmed-middle", "confirmed", created="2026-08-02")
    _write_note(tmp_path, "confirmed-new", "confirmed", created="2026-08-03")
    _write_note(tmp_path, "refuted-later", "refuted", created="2026-08-04")
    _write_note(tmp_path, "untested-latest", "untested", created="2026-08-05")

    entries = get_recent_notes(tmp_path, n=2, status="confirmed")

    assert [entry["title"] for entry in entries] == ["confirmed-middle", "confirmed-new"]


def test_cmd_notes_applies_status_to_normal_list(tmp_path, monkeypatch, capsys) -> None:
    _write_note(tmp_path, "confirmed-note", "confirmed")
    _write_note(tmp_path, "refuted-note", "refuted")
    _write_note(tmp_path, "legacy-note", None)

    out = _run_cmd_notes(tmp_path, monkeypatch, capsys, status="confirmed")

    assert "confirmed-note" in out
    assert "refuted-note" not in out
    assert "legacy-note" not in out


def test_cmd_notes_composes_status_with_search(tmp_path, monkeypatch, capsys) -> None:
    _write_note(tmp_path, "confirmed-tiling", "confirmed")
    _write_note(tmp_path, "refuted-tiling", "refuted")
    _write_note(tmp_path, "confirmed-kernel", "confirmed")

    out = _run_cmd_notes(
        tmp_path,
        monkeypatch,
        capsys,
        search="tiling",
        status="confirmed",
    )

    assert "confirmed-tiling" in out
    assert "refuted-tiling" not in out
    assert "confirmed-kernel" not in out


def test_cmd_notes_recent_filters_before_returning_latest_count(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    _write_note(tmp_path, "confirmed-old", "confirmed", created="2026-08-01")
    _write_note(tmp_path, "confirmed-middle", "confirmed", created="2026-08-02")
    _write_note(tmp_path, "confirmed-new", "confirmed", created="2026-08-03")
    _write_note(tmp_path, "refuted-later", "refuted", created="2026-08-04")
    _write_note(tmp_path, "untested-latest", "untested", created="2026-08-05")

    out = _run_cmd_notes(
        tmp_path,
        monkeypatch,
        capsys,
        recent=2,
        status="confirmed",
    )

    assert "confirmed-old" not in out
    assert "confirmed-middle" in out
    assert "confirmed-new" in out
    assert "refuted-later" not in out
    assert "untested-latest" not in out


def test_cmd_notes_without_status_preserves_existing_list(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    _write_note(tmp_path, "confirmed-note", "confirmed")
    _write_note(tmp_path, "refuted-note", "refuted")
    _write_note(tmp_path, "legacy-note", None)

    out = _run_cmd_notes(tmp_path, monkeypatch, capsys)

    assert out.startswith("Notes (3):\n")
    assert "confirmed-note" in out
    assert "refuted-note" in out
    assert "legacy-note" in out
    assert out.index("confirmed-note") < out.index("legacy-note") < out.index("refuted-note")


def test_cmd_notes_without_status_preserves_existing_search(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    _write_note(tmp_path, "confirmed-tiling", "confirmed")
    _write_note(tmp_path, "refuted-tiling", "refuted")

    out = _run_cmd_notes(tmp_path, monkeypatch, capsys, search="tiling")

    assert out.startswith("Notes matching 'tiling':\n")
    assert "confirmed-tiling" in out
    assert "refuted-tiling" in out
    assert out.index("confirmed-tiling") < out.index("refuted-tiling")


def test_cmd_notes_without_status_preserves_existing_recent(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    _write_note(tmp_path, "confirmed-old", "confirmed", created="2026-08-01")
    _write_note(tmp_path, "refuted-middle", "refuted", created="2026-08-02")
    _write_note(tmp_path, "legacy-new", None, created="2026-08-03")

    out = _run_cmd_notes(tmp_path, monkeypatch, capsys, recent=2)

    assert out.startswith("Recent notes (2):\n")
    assert "confirmed-old" not in out
    assert "refuted-middle" in out
    assert "legacy-new" in out
    assert out.index("refuted-middle") < out.index("legacy-new")


def test_cmd_notes_read_ignores_status_filter(tmp_path, monkeypatch, capsys) -> None:
    _write_note(tmp_path, "confirmed-note", "confirmed", created="2026-08-01")
    _write_note(tmp_path, "refuted-note", "refuted", created="2026-08-02")

    out = _run_cmd_notes(
        tmp_path,
        monkeypatch,
        capsys,
        read="1",
        status="refuted",
    )

    assert "# confirmed-note" in out
    assert "# refuted-note" not in out


def test_notes_help_documents_status_option() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "coral.cli", "notes", "--help"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert "--status STATUS" in result.stdout


def test_notes_rejects_blank_status() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "coral.cli", "notes", "--status", "   "],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 2
    assert "status must be a non-empty string" in result.stderr
