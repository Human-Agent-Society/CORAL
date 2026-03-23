"""Tests for grader system."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

from coral.config import CoralConfig, GraderConfig, TaskConfig
from coral.grader.base import BaseGrader
from coral.grader.builtin.function_grader import FunctionGrader, function_grader
from coral.grader.loader import load_grader
from coral.grader.protocol import GraderInterface
from coral.grader.task_grader import TaskGrader
from coral.types import Score, ScoreBundle, Task


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
    """Create a minimal eval/grader.py for testing the loader."""
    eval_dir = directory / "private" / "eval"
    eval_dir.mkdir(parents=True)
    grader_py = eval_dir / "grader.py"
    grader_py.write_text(
        "from coral.grader.task_grader import TaskGrader\n"
        "class Grader(TaskGrader):\n"
        "    def evaluate(self):\n"
        "        return self.args.get('timeout', 300)\n"
    )


def test_loader_passes_config_timeout():
    """grader.timeout from task.yaml should be available in self.args."""
    with tempfile.TemporaryDirectory() as tmpdir:
        coral_dir = Path(tmpdir)
        _create_grader_file(coral_dir)
        config = CoralConfig(task=TaskConfig(name="t", description="d"))
        config.grader = GraderConfig(timeout=3000)
        grader = load_grader(config, coral_dir)
        assert grader.args["timeout"] == 3000


def test_loader_args_timeout_overrides_config():
    """Explicit grader.args.timeout should take precedence over grader.timeout."""
    with tempfile.TemporaryDirectory() as tmpdir:
        coral_dir = Path(tmpdir)
        _create_grader_file(coral_dir)
        config = CoralConfig(task=TaskConfig(name="t", description="d"))
        config.grader = GraderConfig(timeout=3000, args={"timeout": 5000})
        grader = load_grader(config, coral_dir)
        assert grader.args["timeout"] == 5000
