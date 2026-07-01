"""Tests for task-directory validation (coral validate / coral start)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from coral.cli.validation import validate_task

_TASK_YAML = """\
task:
  name: t
  description: d
grader:
{grader_body}
agents:
  count: 1
"""


def _make_task(base: Path, grader_body: str) -> Path:
    task_dir = base / "task"
    task_dir.mkdir()
    (task_dir / "task.yaml").write_text(_TASK_YAML.format(grader_body=grader_body))
    return task_dir


def test_validate_accepts_entrypoint():
    with tempfile.TemporaryDirectory() as d:
        task_dir = _make_task(Path(d), '  entrypoint: "my_pkg.grader:Grader"')
        assert validate_task(task_dir) == []


def test_validate_rejects_missing_entrypoint():
    with tempfile.TemporaryDirectory() as d:
        task_dir = _make_task(Path(d), "  timeout: 60")
        errors = validate_task(task_dir)
        assert any("No grader configured" in e for e in errors)


def test_validate_rejects_malformed_entrypoint():
    with tempfile.TemporaryDirectory() as d:
        task_dir = _make_task(Path(d), "  entrypoint: my_pkg.grader.Grader")
        errors = validate_task(task_dir)
        assert any("module.path:ClassName" in e for e in errors)


def _make_task_with_dirs(base: Path, grader_body: str, dirs: list[str]) -> Path:
    task_dir = base / "task"
    task_dir.mkdir()
    (task_dir / "task.yaml").write_text(_TASK_YAML.format(grader_body=grader_body))
    (task_dir / "grader").mkdir()
    for rel in dirs:
        (task_dir / rel).mkdir(parents=True, exist_ok=True)
    return task_dir


def test_validate_accepts_private_sibling_of_grader():
    """The common, safe layout: hidden data beside grader/ (e.g. taskdata/)."""
    body = '  entrypoint: "p.g:G"\n  private:\n    - "taskdata"'
    with tempfile.TemporaryDirectory() as d:
        task_dir = _make_task_with_dirs(Path(d), body, ["taskdata"])
        assert validate_task(task_dir) == []


def test_validate_rejects_private_inside_grader_package():
    """A grader.private path inside grader/ would be surfaced to agents via
    <shared_dir>/grader/ — validate must flag it as a leak."""
    body = '  entrypoint: "p.g:G"\n  private:\n    - "grader/taskdata"'
    with tempfile.TemporaryDirectory() as d:
        task_dir = _make_task_with_dirs(Path(d), body, ["grader/taskdata"])
        errors = validate_task(task_dir)
        assert any("inside the grader package" in e for e in errors)
        assert any("grader/taskdata" in e for e in errors)
