from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def evaluate(program_path: str, *, repo_root: Path | None = None):
    start = time.time()
    repo_root = (repo_root or Path.cwd()).expanduser().resolve()
    program_path_p = Path(program_path).expanduser().resolve()

    benchmark_dir = (
        repo_root / "benchmarks" / "Robotics" / "QuadrupedGaitOptimization"
    ).resolve()
    if not benchmark_dir.is_dir():
        benchmark_dir = (repo_root / "Robotics" / "QuadrupedGaitOptimization").resolve()

    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "valid": 0.0,
        "timeout": 0.0,
        "runtime_s": 0.0,
    }
    artifacts: dict[str, str] = {}

    if not benchmark_dir.is_dir():
        artifacts["error_message"] = f"benchmark dir not found: {benchmark_dir}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    if not program_path_p.is_file():
        artifacts["error_message"] = f"program not found: {program_path_p}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    evaluator_timeout_s = float(os.environ.get("FRONTIER_EVAL_EVALUATOR_TIMEOUT_S", "240") or "240")
    work_dir = Path(tempfile.mkdtemp(prefix="fe_quadruped_")).resolve()
    try:
        sandbox_program = work_dir / "solution.py"
        sandbox_submission = work_dir / "submission.json"
        shutil.copy2(program_path_p, sandbox_program)

        try:
            proc = subprocess.run(
                [sys.executable, str(sandbox_program)],
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=max(1.0, evaluator_timeout_s),
            )
        except subprocess.TimeoutExpired as exc:
            metrics["timeout"] = 1.0
            artifacts["error_message"] = f"candidate timeout: {exc}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        artifacts["candidate_stdout"] = proc.stdout[-8000:]
        artifacts["candidate_stderr"] = proc.stderr[-8000:]
        metrics["candidate_returncode"] = float(proc.returncode)
        if proc.returncode != 0:
            artifacts["error_message"] = "candidate program exited non-zero"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)
        if not sandbox_submission.is_file():
            artifacts["error_message"] = "candidate did not generate submission.json"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        eval_path = (benchmark_dir / "verification" / "evaluator.py").resolve()
        spec = importlib.util.spec_from_file_location("fe_quadruped_eval", eval_path)
        if spec is None or spec.loader is None:
            artifacts["error_message"] = f"failed to load evaluator: {eval_path}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        benchmark_evaluate = getattr(module, "evaluate")

        raw_speed = float(benchmark_evaluate(sandbox_submission))
        feasible = raw_speed > 0.0
        metrics["feasible"] = 1.0 if feasible else 0.0
        if feasible:
            metrics["valid"] = 1.0
            metrics["speed_mps"] = raw_speed
            metrics["combined_score"] = raw_speed
        else:
            artifacts["error_message"] = "infeasible gait"

        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _wrap(metrics: dict[str, float], artifacts: dict[str, str]):
    try:
        from openevolve.evaluation_result import EvaluationResult
    except Exception:
        return {"metrics": metrics, "artifacts": artifacts}
    return EvaluationResult(metrics=metrics, artifacts=artifacts)
