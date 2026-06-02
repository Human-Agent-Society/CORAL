"""Tests for grader system."""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

import pytest

from coral.config import CoralConfig, GraderConfig, TaskConfig
from coral.grader.builtin.function_grader import FunctionGrader, function_grader
from coral.grader.loader import load_grader
from coral.grader.protocol import GraderInterface
from coral.grader.subprocess_grader import SubprocessGrader
from coral.grader.task_grader import DEFAULT_TUNE_DESCRIPTION, TaskGrader
from coral.types import ScoreBundle, Task

# --- Harbor grader schema tests (swebench-verified, terminal-bench) ----------
#
# These graders parse harbor v0.13's job result.json. The schema moved
# `n_trials` from the top level (and from `stats`) into `stats.n_completed_trials`
# — graders that read the old `n_trials` field hit an early "No trials completed"
# return and score 0.0 even when trials actually completed and passed.
# Regression: attempt 172a1463 ran 5 swebench trials, 2 passed (40%),
# but the grader returned 0.0 because `stats["n_trials"]` was None.
_EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _import_grader(task_dir_name: str, module: str):
    """Import a task's grader module by adding its src/ to sys.path.

    Avoids needing an editable install of the grader package for the test suite.
    """
    src = _EXAMPLES / task_dir_name / "grader" / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return __import__(module, fromlist=["Grader"])


def _swebench_grader():
    return _import_grader("swebench-verified", "swebench_verified_grader.grader").Grader


def _terminal_bench_grader():
    return _import_grader("terminal-bench", "terminal_bench_grader.grader").Grader


def _make_swebench_result(n_completed: int = 5, n_passed: int = 2) -> dict:
    """Build a synthetic harbor v0.13 job result.json payload (swebench shape)."""
    return {
        "id": "test-job",
        "started_at": "2026-06-02T00:00:00+00:00",
        "finished_at": "2026-06-02T00:30:00+00:00",
        "updated_at": "2026-06-02T00:30:00+00:00",
        "n_total_trials": n_completed,
        "n_errors": None,
        "stats": {
            "n_completed_trials": n_completed,
            "n_errored_trials": 0,
            "n_pending_trials": 0,
            "n_running_trials": 0,
            "n_cancelled_trials": 0,
            "n_retries": 0,
            "n_cache_tokens": 0,
            "n_input_tokens": 0,
            "n_output_tokens": 0,
            "cost_usd": 0.0,
            "evals": {
                "terminus-2__MiniMax-M3__swebench-verified": {
                    "n_trials": n_completed,
                    "n_errors": 0,
                    "pass_at_k": {},  # harbor v0.13 leaves this empty for swebench
                    "reward_stats": {
                        "reward": {
                            "1.0": [f"trial-{i}" for i in range(n_passed)],
                            "0.0": [f"trial-{i}" for i in range(n_passed, n_completed)],
                        }
                    },
                    "exception_stats": {},
                    "metrics": {},
                }
            },
        },
    }


def _make_terminal_bench_result(n_completed: int = 4, n_passed: int = 2) -> dict:
    """Build a synthetic harbor v0.13 job result.json payload (terminal-bench shape)."""
    return {
        "id": "test-job",
        "started_at": "2026-06-02T00:00:00+00:00",
        "finished_at": "2026-06-02T00:30:00+00:00",
        "updated_at": "2026-06-02T00:30:00+00:00",
        "n_total_trials": n_completed,
        "n_errors": None,
        "stats": {
            "n_completed_trials": n_completed,
            "n_errored_trials": 0,
            "n_pending_trials": 0,
            "n_running_trials": 0,
            "n_cancelled_trials": 0,
            "n_retries": 0,
            "n_cache_tokens": 0,
            "n_input_tokens": 0,
            "n_output_tokens": 0,
            "cost_usd": 0.0,
            "evals": {
                "terminus-2__MiniMax-M3__terminal-bench": {
                    "n_trials": n_completed,
                    "n_errors": 0,
                    "pass_at_k": {"1": n_passed / n_completed if n_completed else 0.0},
                    "reward_stats": {
                        "reward": {
                            "1.0": [f"trial-{i}" for i in range(n_passed)],
                            "0.0": [f"trial-{i}" for i in range(n_passed, n_completed)],
                        }
                    },
                    "exception_stats": {},
                    "metrics": {},
                }
            },
        },
    }


def test_swebench_parse_job_result_uses_completed_trials():
    """Grader must read stats.n_completed_trials, not the legacy n_trials field.

    Regression: attempt 172a1463 (5 trials, 2 passed → 40%) was scored 0.0
    because the old code did `stats.get("n_trials", 0)` which is None in
    harbor v0.13, triggering the "No trials completed" early return.
    """
    grader_cls = _swebench_grader()
    grader = grader_cls.__new__(grader_cls)  # bypass __init__ — _parse_job_result is pure
    grader.config = GraderConfig(args={})

    with tempfile.TemporaryDirectory() as job_dir:
        job_dir_p = Path(job_dir)
        result = _make_swebench_result(n_completed=5, n_passed=2)
        pass_rate, feedback = grader._parse_job_result(
            result, job_dir_p, elapsed=1983.0, tier_name="Tier 1"
        )

    assert pass_rate == pytest.approx(0.4), (
        f"expected 2/5 = 40% pass rate, got {pass_rate:.1%}. "
        "Did n_completed_trials get parsed correctly?"
    )
    assert "Completed 5 trials" in feedback
    assert "No trials completed" not in feedback


def test_swebench_parse_job_result_zero_completed_returns_zero():
    """If n_completed_trials really is 0 (eval was a total failure), score 0.0."""
    grader_cls = _swebench_grader()
    grader = grader_cls.__new__(grader_cls)
    grader.config = GraderConfig(args={})

    with tempfile.TemporaryDirectory() as job_dir:
        result = _make_swebench_result(n_completed=0, n_passed=0)
        pass_rate, feedback = grader._parse_job_result(
            result, Path(job_dir), elapsed=60.0, tier_name="Tier 1"
        )

    assert pass_rate == 0.0
    assert "No trials completed" in feedback


def test_swebench_parse_with_real_harbor_result():
    """Round-trip the actual result.json from the regression-1 attempt.

    attempt 172a1463 ran 5 swebench trials, 2 passed, and the grader scored
    it 0.0 due to the n_trials field mismatch. This test pins the corrected
    behavior — the real harbor output now parses to 0.4 (2/5).

    Skipped if results/ is missing (e.g. CI without local eval logs).
    """
    repo_root = Path(__file__).resolve().parent.parent
    target = (
        repo_root / "results" / "swebench-verified" / "latest" / ".coral" / "public" / "eval_logs"
    )
    real = None
    for p in target.glob("*/harbor_logs/eval_*/result.json"):
        if p.parent.parent.parent.name.startswith("172a1463"):
            real = p
            break
    if real is None:
        pytest.skip("results for attempt 172a1463 not present")
    job_dir = real.parent

    grader_cls = _swebench_grader()
    grader = grader_cls.__new__(grader_cls)
    grader.config = GraderConfig(args={})

    job_result = json.loads(real.read_text())
    pass_rate, feedback = grader._parse_job_result(
        job_result, job_dir, elapsed=1983.0, tier_name="Tier 1"
    )
    # The saved attempt had 5 trials, 2 passing (per reward_stats) → 0.4.
    assert pass_rate == pytest.approx(0.4), f"expected 0.4 from real harbor output, got {pass_rate}"
    assert "No trials completed" not in feedback


def test_terminal_bench_parse_job_result_uses_completed_trials():
    """Same regression as swebench, for terminal-bench grader."""
    grader_cls = _terminal_bench_grader()
    grader = grader_cls.__new__(grader_cls)
    grader.config = GraderConfig(args={})

    with tempfile.TemporaryDirectory() as job_dir:
        result = _make_terminal_bench_result(n_completed=4, n_passed=2)
        pass_rate, feedback = grader._parse_job_result(
            result, Path(job_dir), elapsed=1200.0, tier_name="Tier 1"
        )

    assert pass_rate == pytest.approx(0.5), f"expected 2/4 = 50% pass rate, got {pass_rate:.1%}"
    assert "Completed 4 trials" in feedback
    assert "No trials completed" not in feedback


def test_terminal_bench_parse_job_result_zero_completed_returns_zero():
    grader_cls = _terminal_bench_grader()
    grader = grader_cls.__new__(grader_cls)
    grader.config = GraderConfig(args={})

    with tempfile.TemporaryDirectory() as job_dir:
        result = _make_terminal_bench_result(n_completed=0, n_passed=0)
        pass_rate, feedback = grader._parse_job_result(
            result, Path(job_dir), elapsed=60.0, tier_name="Tier 1"
        )

    assert pass_rate == 0.0
    assert "No trials completed" in feedback


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


def _real_task() -> Task:
    return Task(id="t", name="t", description="d", metadata={"budget_class": "real"})


def _tune_task() -> Task:
    return Task(id="t", name="t", description="d", metadata={"budget_class": "tune"})


class _StaticGrader(TaskGrader):
    """Returns a hand-built ScoreBundle so tests can probe feedback exactly."""

    def __init__(self, config: GraderConfig, bundle: ScoreBundle) -> None:
        super().__init__(config=config)
        self._bundle = bundle

    def evaluate(self) -> ScoreBundle:
        return self._bundle


class _OverrideTuneGrader(_StaticGrader):
    def describe_tune(self) -> str:
        return "scored on a 10% slice; ~30s instead of ~5m"


def test_grade_does_not_annotate_real_attempts():
    """Real attempts must not get a [--tune mode] prefix in feedback."""
    grader = _StaticGrader(
        config=GraderConfig(),
        bundle=ScoreBundle(scores={}, aggregated=0.5, feedback="ok"),
    )
    bundle = asyncio.run(grader.grade("/tmp/x", [_real_task()]))
    assert bundle.feedback == "ok"


def test_grade_annotates_tune_attempts_with_default_description():
    """Tune attempts get the default describe_tune text prepended to feedback."""
    grader = _StaticGrader(
        config=GraderConfig(),
        bundle=ScoreBundle(scores={}, aggregated=0.5, feedback="raw eval feedback"),
    )
    bundle = asyncio.run(grader.grade("/tmp/x", [_tune_task()]))
    assert bundle.feedback is not None
    assert bundle.feedback.startswith("[--tune mode]")
    assert DEFAULT_TUNE_DESCRIPTION in bundle.feedback
    assert "raw eval feedback" in bundle.feedback


def test_grade_annotates_tune_attempts_with_overridden_description():
    """Per-grader override is what the agent sees."""
    grader = _OverrideTuneGrader(
        config=GraderConfig(),
        bundle=ScoreBundle(scores={}, aggregated=0.5, feedback=None),
    )
    bundle = asyncio.run(grader.grade("/tmp/x", [_tune_task()]))
    assert bundle.feedback == "[--tune mode] scored on a 10% slice; ~30s instead of ~5m"
    # Default text must NOT appear once a grader overrides describe_tune.
    assert DEFAULT_TUNE_DESCRIPTION not in bundle.feedback


def test_grade_annotates_tune_attempts_when_evaluate_returns_float():
    """Feedback annotation also fires when evaluate() returns a bare float."""

    class _FloatGrader(TaskGrader):
        def evaluate(self) -> float:
            return 0.42

    grader = _FloatGrader(config=GraderConfig())
    bundle = asyncio.run(grader.grade("/tmp/x", [_tune_task()]))
    assert bundle.aggregated == pytest.approx(0.42)
    assert bundle.feedback is not None
    assert bundle.feedback.startswith("[--tune mode]")


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
