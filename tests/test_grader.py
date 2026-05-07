"""Tests for grader system."""

import tempfile
from pathlib import Path

import pytest

from coral.config import CoralConfig, GraderConfig, TaskConfig
from coral.grader.builtin.function_grader import FunctionGrader, function_grader
from coral.grader.loader import load_grader
from coral.grader.protocol import GraderInterface
from coral.grader.subprocess_grader import SubprocessGrader
from coral.types import Task


def test_function_grader_sync():
    def my_grader(codebase_path: str, tasks: list[Task]) -> float:
        return 0.85

    grader = FunctionGrader(name="test", func=my_grader)
    result = grader.grade_sync("/tmp/test", [Task(id="t1", name="t", description="d")])
    assert result.aggregated == 0.85


def test_function_grader_bool():
    def my_grader(codebase_path: str, tasks: list[Task]) -> bool:
        return True

    grader = FunctionGrader(name="test", func=my_grader)
    result = grader.grade_sync("/tmp/test", [Task(id="t1", name="t", description="d")])
    assert result.aggregated == 1.0


def test_function_grader_decorator():
    @function_grader("decorated")
    def my_grader(codebase_path, tasks):
        return 0.5

    assert isinstance(my_grader, FunctionGrader)
    result = my_grader.grade_sync("/tmp/test", [Task(id="t1", name="t", description="d")])
    assert result.aggregated == 0.5


def test_grader_protocol_compliance():
    def my_grader(codebase_path: str, tasks: list[Task]) -> float:
        return 0.5

    grader = FunctionGrader(name="test", func=my_grader)
    assert isinstance(grader, GraderInterface)


def _create_grader_file(directory: Path) -> None:
    """Create a minimal eval/grader.py for testing the legacy loader path."""
    eval_dir = directory / "private" / "eval"
    eval_dir.mkdir(parents=True)
    grader_py = eval_dir / "grader.py"
    grader_py.write_text(
        "from coral.grader.task_grader import TaskGrader\n"
        "class Grader(TaskGrader):\n"
        "    def evaluate(self):\n"
        "        return self.timeout\n"
    )


def test_loader_passes_grader_config():
    """GraderConfig from task.yaml should be accessible as self.config (legacy path)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        coral_dir = Path(tmpdir)
        _create_grader_file(coral_dir)
        config = CoralConfig(task=TaskConfig(name="t", description="d"))
        config.grader = GraderConfig(timeout=3000)
        with pytest.warns(DeprecationWarning):
            grader = load_grader(config, coral_dir)
        assert grader.config is config.grader
        assert grader.timeout == 3000


def test_loader_passes_args_separately():
    """grader.args should reach the loaded grader (legacy path)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        coral_dir = Path(tmpdir)
        _create_grader_file(coral_dir)
        config = CoralConfig(task=TaskConfig(name="t", description="d"))
        config.grader = GraderConfig(timeout=3000, args={"program_file": "sol.py"})
        with pytest.warns(DeprecationWarning):
            grader = load_grader(config, coral_dir)
        assert grader.timeout == 3000
        assert grader.args["program_file"] == "sol.py"


def test_loader_eval_grader_py_emits_deprecation_warning():
    """Loading via eval/grader.py must emit DeprecationWarning."""
    with tempfile.TemporaryDirectory() as tmpdir:
        coral_dir = Path(tmpdir)
        _create_grader_file(coral_dir)
        config = CoralConfig(task=TaskConfig(name="t", description="d"))
        with pytest.warns(DeprecationWarning, match="eval/grader.py"):
            load_grader(config, coral_dir)


def test_loader_returns_subprocess_grader_for_entrypoint():
    """When grader.entrypoint is set, loader returns a SubprocessGrader."""
    with tempfile.TemporaryDirectory() as tmpdir:
        coral_dir = Path(tmpdir)
        # Pretend the grader venv exists.
        venv_python = coral_dir / "private" / "grader_venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        venv_python.touch()

        config = CoralConfig(task=TaskConfig(name="t", description="d"))
        config.grader = GraderConfig(entrypoint="my_pkg.grader:Grader", timeout=42)
        grader = load_grader(config, coral_dir)

        assert isinstance(grader, SubprocessGrader)
        assert grader.entrypoint == "my_pkg.grader:Grader"
        assert grader.worker_python == venv_python
        assert grader.timeout == 42
        assert grader.private_dir == str(coral_dir / "private")


def test_loader_raises_when_entrypoint_set_but_venv_missing():
    """Helpful error when the user forgot to call setup_grader_env first."""
    with tempfile.TemporaryDirectory() as tmpdir:
        coral_dir = Path(tmpdir)
        config = CoralConfig(task=TaskConfig(name="t", description="d"))
        config.grader = GraderConfig(entrypoint="my_pkg:Grader")
        with pytest.raises(RuntimeError, match="grader venv not initialized|venv|setup_grader_env"):
            load_grader(config, coral_dir)


def test_loader_raises_when_no_grader_configured():
    """No entrypoint and no eval/grader.py → ValueError with migration hint."""
    with tempfile.TemporaryDirectory() as tmpdir:
        coral_dir = Path(tmpdir)
        config = CoralConfig(task=TaskConfig(name="t", description="d"))
        with pytest.raises(ValueError, match="entrypoint"):
            load_grader(config, coral_dir)
