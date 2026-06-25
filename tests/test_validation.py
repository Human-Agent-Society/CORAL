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


def _make_task_yaml(base: Path, yaml: str) -> Path:
    task_dir = base / "task"
    task_dir.mkdir()
    (task_dir / "task.yaml").write_text(yaml)
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


def test_validate_rejects_private_inside_repo_path():
    with tempfile.TemporaryDirectory() as d:
        task_dir = _make_task_yaml(
            Path(d),
            """\
task:
  name: t
  description: d
workspace:
  repo_path: "."
grader:
  entrypoint: "my_pkg.grader:Grader"
  private:
    - hidden/answer.txt
agents:
  count: 1
""",
        )
        hidden = task_dir / "hidden"
        hidden.mkdir()
        (hidden / "answer.txt").write_text("secret")

        errors = validate_task(task_dir)

        assert any("grader.private" in e and "workspace.repo_path" in e for e in errors)


def test_validate_rejects_private_inside_repo_path_resolved_from_run_cwd():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        task_dir = _make_task_yaml(
            root,
            """\
task:
  name: t
  description: d
workspace:
  repo_path: "."
grader:
  entrypoint: "my_pkg.grader:Grader"
  private:
    - ../hidden/answer.txt
agents:
  count: 1
""",
        )
        hidden = root / "hidden"
        hidden.mkdir()
        (hidden / "answer.txt").write_text("secret")

        errors = validate_task(task_dir, repo_base_dir=root)

        assert any("grader.private" in e and "workspace.repo_path" in e for e in errors)


def test_validate_rejects_repo_path_inside_private_dir():
    with tempfile.TemporaryDirectory() as d:
        task_dir = _make_task_yaml(
            Path(d),
            """\
task:
  name: t
  description: d
workspace:
  repo_path: hidden/seed
grader:
  entrypoint: "my_pkg.grader:Grader"
  private:
    - hidden
agents:
  count: 1
""",
        )
        hidden = task_dir / "hidden"
        (hidden / "seed").mkdir(parents=True)
        (hidden / "answer.txt").write_text("secret")

        errors = validate_task(task_dir)

        assert any("grader.private" in e and "workspace.repo_path" in e for e in errors)


def test_validate_accepts_private_outside_seed_repo_path():
    with tempfile.TemporaryDirectory() as d:
        task_dir = _make_task_yaml(
            Path(d),
            """\
task:
  name: t
  description: d
workspace:
  repo_path: seed
grader:
  entrypoint: "my_pkg.grader:Grader"
  private:
    - hidden/answer.txt
agents:
  count: 1
""",
        )
        (task_dir / "seed").mkdir()
        hidden = task_dir / "hidden"
        hidden.mkdir()
        (hidden / "answer.txt").write_text("secret")

        assert validate_task(task_dir) == []


def test_validate_rejects_runtime_mount_that_overlaps_private():
    with tempfile.TemporaryDirectory() as d:
        task_dir = _make_task_yaml(
            Path(d),
            """\
task:
  name: t
  description: d
workspace:
  repo_path: seed
grader:
  entrypoint: "my_pkg.grader:Grader"
  private:
    - hidden/answer.txt
agents:
  count: 1
  runtime_options:
    mounts:
      hidden: .codex/hidden
""",
        )
        (task_dir / "seed").mkdir()
        hidden = task_dir / "hidden"
        hidden.mkdir()
        (hidden / "answer.txt").write_text("secret")

        errors = validate_task(task_dir)

        assert any("runtime_options.mounts" in e and "grader.private" in e for e in errors)


def test_validate_rejects_claude_add_dir_that_overlaps_private():
    with tempfile.TemporaryDirectory() as d:
        task_dir = _make_task_yaml(
            Path(d),
            """\
task:
  name: t
  description: d
workspace:
  repo_path: seed
grader:
  entrypoint: "my_pkg.grader:Grader"
  private:
    - hidden/answer.txt
agents:
  count: 1
  runtime: claude_code
  runtime_options:
    add_dirs:
      - hidden
""",
        )
        (task_dir / "seed").mkdir()
        hidden = task_dir / "hidden"
        hidden.mkdir()
        (hidden / "answer.txt").write_text("secret")

        errors = validate_task(task_dir)

        assert any("runtime_options.add_dirs" in e and "grader.private" in e for e in errors)


def test_validate_rejects_role_file_that_overlaps_private():
    with tempfile.TemporaryDirectory() as d:
        task_dir = _make_task_yaml(
            Path(d),
            """\
task:
  name: t
  description: d
workspace:
  repo_path: seed
grader:
  entrypoint: "my_pkg.grader:Grader"
  private:
    - hidden
agents:
  count: 1
  runtime_options:
    role_file: hidden/role.md
""",
        )
        (task_dir / "seed").mkdir()
        hidden = task_dir / "hidden"
        hidden.mkdir()
        (hidden / "role.md").write_text("secret role")

        errors = validate_task(task_dir)

        assert any("runtime_options.role_file" in e and "grader.private" in e for e in errors)


def test_validate_rejects_assignment_runtime_mount_that_overlaps_private():
    with tempfile.TemporaryDirectory() as d:
        task_dir = _make_task_yaml(
            Path(d),
            """\
task:
  name: t
  description: d
workspace:
  repo_path: seed
grader:
  entrypoint: "my_pkg.grader:Grader"
  private:
    - hidden/answer.txt
agents:
  assignments:
    - runtime: codex
      count: 1
      runtime_options:
        mounts:
          hidden: .codex/hidden
""",
        )
        (task_dir / "seed").mkdir()
        hidden = task_dir / "hidden"
        hidden.mkdir()
        (hidden / "answer.txt").write_text("secret")

        errors = validate_task(task_dir)

        assert any(
            "agents.assignments[0].runtime_options.mounts" in e and "grader.private" in e
            for e in errors
        )
