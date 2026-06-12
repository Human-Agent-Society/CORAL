"""Tests for SubprocessGrader (entrypoint-based grader execution).

Uses the current Python interpreter as the worker (CORAL's own venv) and
injects a fixture grader via PYTHONPATH. Real grader-venv tests live in
test_grader_env.py + the migrated example smoke tests.
"""

from __future__ import annotations

import asyncio
import os
import sys
import textwrap
from pathlib import Path

import pytest

from coral.config import GraderConfig
from coral.grader.subprocess_grader import SubprocessGrader
from coral.types import Task


def _write_fixture_grader(dir_path: Path, body: str) -> None:
    """Write a fixture grader package at `dir_path/fixture_grader/__init__.py`."""
    pkg = dir_path / "fixture_grader"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text(textwrap.dedent(body))


@pytest.fixture
def pythonpath_with(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Prepend tmp_path to PYTHONPATH so the worker subprocess can import fixtures."""
    existing = os.environ.get("PYTHONPATH", "")
    new = f"{tmp_path}{os.pathsep}{existing}" if existing else str(tmp_path)
    monkeypatch.setenv("PYTHONPATH", new)
    return tmp_path


def _grade(grader: SubprocessGrader, codebase_path: str, tasks: list[Task] | None = None):
    return asyncio.run(grader.grade(codebase_path, tasks or []))


def test_subprocess_grader_returns_score(pythonpath_with: Path) -> None:
    _write_fixture_grader(
        pythonpath_with,
        """
        from coral.grader import TaskGrader

        class Grader(TaskGrader):
            def evaluate(self) -> float:
                return float(self.args["score"])
        """,
    )

    grader = SubprocessGrader(
        entrypoint="fixture_grader:Grader",
        worker_python=Path(sys.executable),
        config=GraderConfig(args={"score": 0.42}),
        private_dir=str(pythonpath_with / "private"),
    )

    bundle = _grade(grader, str(pythonpath_with))

    assert bundle.aggregated == pytest.approx(0.42)
    assert bundle.scores["eval"].value == pytest.approx(0.42)


def test_subprocess_grader_propagates_codebase_and_private_dir(pythonpath_with: Path) -> None:
    _write_fixture_grader(
        pythonpath_with,
        """
        from coral.grader import TaskGrader

        class Grader(TaskGrader):
            def evaluate(self) -> float:
                # Encode the two strings into a deterministic float for the assertion.
                assert self.codebase_path == self.args["expect_codebase"]
                assert self.private_dir == self.args["expect_private_dir"]
                return 1.0
        """,
    )

    codebase = str(pythonpath_with / "code")
    private = str(pythonpath_with / "secret")
    grader = SubprocessGrader(
        entrypoint="fixture_grader:Grader",
        worker_python=Path(sys.executable),
        config=GraderConfig(args={"expect_codebase": codebase, "expect_private_dir": private}),
        private_dir=private,
    )

    bundle = _grade(grader, codebase)
    assert bundle.aggregated == pytest.approx(1.0)


def test_subprocess_grader_unknown_module_raises(pythonpath_with: Path) -> None:
    grader = SubprocessGrader(
        entrypoint="not_a_real_module:Grader",
        worker_python=Path(sys.executable),
        config=GraderConfig(),
        private_dir=str(pythonpath_with),
    )
    with pytest.raises(RuntimeError, match="not_a_real_module"):
        _grade(grader, str(pythonpath_with))


def test_subprocess_grader_unknown_class_raises(pythonpath_with: Path) -> None:
    _write_fixture_grader(
        pythonpath_with,
        """
        from coral.grader import TaskGrader

        class NotGrader(TaskGrader):
            def evaluate(self):
                return 0.0
        """,
    )
    grader = SubprocessGrader(
        entrypoint="fixture_grader:DoesNotExist",
        worker_python=Path(sys.executable),
        config=GraderConfig(),
        private_dir=str(pythonpath_with),
    )
    with pytest.raises(RuntimeError, match="DoesNotExist"):
        _grade(grader, str(pythonpath_with))


def test_subprocess_grader_malformed_entrypoint_raises(pythonpath_with: Path) -> None:
    grader = SubprocessGrader(
        entrypoint="missing_colon",
        worker_python=Path(sys.executable),
        config=GraderConfig(),
        private_dir=str(pythonpath_with),
    )
    with pytest.raises(RuntimeError, match="entrypoint"):
        _grade(grader, str(pythonpath_with))


def test_subprocess_grader_non_taskgrader_raises(pythonpath_with: Path) -> None:
    _write_fixture_grader(
        pythonpath_with,
        """
        class Grader:  # NOT a TaskGrader subclass
            def __init__(self, config): pass
        """,
    )
    grader = SubprocessGrader(
        entrypoint="fixture_grader:Grader",
        worker_python=Path(sys.executable),
        config=GraderConfig(),
        private_dir=str(pythonpath_with),
    )
    with pytest.raises(RuntimeError, match="TaskGrader"):
        _grade(grader, str(pythonpath_with))


def test_subprocess_grader_propagates_grader_exception(pythonpath_with: Path) -> None:
    _write_fixture_grader(
        pythonpath_with,
        """
        from coral.grader import TaskGrader

        class Grader(TaskGrader):
            def evaluate(self):
                raise ValueError("boom from grader")
        """,
    )
    grader = SubprocessGrader(
        entrypoint="fixture_grader:Grader",
        worker_python=Path(sys.executable),
        config=GraderConfig(),
        private_dir=str(pythonpath_with),
    )
    with pytest.raises(RuntimeError, match="boom from grader"):
        _grade(grader, str(pythonpath_with))


def test_subprocess_grader_timeout_raises_timeout_error(pythonpath_with: Path) -> None:
    """A hung worker is killed at grader.timeout and surfaces as TimeoutError,
    which the daemon classifies as status="timeout" / budget_class="grader_error"."""
    _write_fixture_grader(
        pythonpath_with,
        """
        import time
        from coral.grader import TaskGrader

        class Grader(TaskGrader):
            def evaluate(self):
                time.sleep(60)
                return 1.0
        """,
    )
    grader = SubprocessGrader(
        entrypoint="fixture_grader:Grader",
        worker_python=Path(sys.executable),
        config=GraderConfig(timeout=1),
        private_dir=str(pythonpath_with),
    )
    with pytest.raises(TimeoutError, match="timed out"):
        _grade(grader, str(pythonpath_with))


def test_subprocess_grader_propagates_island_id(pythonpath_with: Path) -> None:
    """Regression: the inner grader must see ``island_id`` on ``self`` so it
    can scope hub reads (e.g. ``read_attempts(coral_dir, island_id=...)``)
    in multi-island runs. Pre-fix, the worker payload didn't include
    ``island_id`` and multi-island graders crashed with
    ``ValueError: island_id is required in multi-island runs``."""
    _write_fixture_grader(
        pythonpath_with,
        """
        from coral.grader import TaskGrader

        class Grader(TaskGrader):
            def evaluate(self) -> float:
                # The inner grader.grade() should have set self.island_id
                # from the kwargs the parent passed.
                assert self.island_id == self.args["expect_island_id"]
                return 0.0
        """,
    )
    grader = SubprocessGrader(
        entrypoint="fixture_grader:Grader",
        worker_python=Path(sys.executable),
        config=GraderConfig(args={"expect_island_id": "2"}),
        private_dir=str(pythonpath_with),
    )
    bundle = asyncio.run(grader.grade(str(pythonpath_with), [], island_id="2"))
    assert bundle.aggregated == 0.0


def test_subprocess_grader_island_id_defaults_to_none(pythonpath_with: Path) -> None:
    """Single-island mode (no ``island_id`` kwarg) must leave
    ``self.island_id`` at None so single-island graders behave exactly as
    before. The legacy payload shape (no ``island_id`` key) is preserved."""
    _write_fixture_grader(
        pythonpath_with,
        """
        from coral.grader import TaskGrader

        class Grader(TaskGrader):
            def evaluate(self) -> float:
                assert self.island_id is None
                return 0.0
        """,
    )
    grader = SubprocessGrader(
        entrypoint="fixture_grader:Grader",
        worker_python=Path(sys.executable),
        config=GraderConfig(),
        private_dir=str(pythonpath_with),
    )
    bundle = _grade(grader, str(pythonpath_with))
    assert bundle.aggregated == 0.0
