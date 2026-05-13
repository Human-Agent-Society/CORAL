from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

INVALID_COMBINED_SCORE = -1e18


def evaluate(program_path: str, *, repo_root: Path | None = None):
    start = time.time()
    repo_root = (repo_root or Path.cwd()).expanduser().resolve()
    program_path_p = Path(program_path).expanduser().resolve()

    benchmark_dir = (
        repo_root / "benchmarks" / "Robotics" / "UAVInspectionCoverageWithWind"
    ).resolve()
    if not benchmark_dir.is_dir():
        benchmark_dir = (repo_root / "Robotics" / "UAVInspectionCoverageWithWind").resolve()

    metrics: dict[str, float] = {
        "combined_score": INVALID_COMBINED_SCORE,
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
    work_dir = Path(tempfile.mkdtemp(prefix="fe_uavcov_")).resolve()
    try:
        sandbox_task = (work_dir / "UAVInspectionCoverageWithWind").resolve()
        shutil.copytree(benchmark_dir, sandbox_task)

        sandbox_program = (sandbox_task / "baseline" / "solution.py").resolve()
        sandbox_submission = (sandbox_task / "baseline" / "submission.json").resolve()
        shutil.copy2(program_path_p, sandbox_program)

        try:
            proc = subprocess.run(
                [sys.executable, str(sandbox_program)],
                cwd=str(sandbox_task / "baseline"),
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

        eval_path = (sandbox_task / "verification" / "evaluator.py").resolve()
        spec = importlib.util.spec_from_file_location("fe_uav_coverage_eval", eval_path)
        if spec is None or spec.loader is None:
            artifacts["error_message"] = f"failed to load evaluator: {eval_path}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        benchmark_evaluate = getattr(module, "evaluate")

        result: dict[str, Any] = benchmark_evaluate(sandbox_submission)
        artifacts["evaluation_result"] = json.dumps(result, ensure_ascii=False)

        feasible = bool(result.get("feasible", False))
        metrics["feasible"] = 1.0 if feasible else 0.0
        if feasible:
            raw_score = float(result["score"])
            metrics["valid"] = 1.0
            metrics["coverage_objective"] = raw_score
            metrics["combined_score"] = raw_score
        else:
            artifacts["error_message"] = "infeasible UAV trajectory"

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
