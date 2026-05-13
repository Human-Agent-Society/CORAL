from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


DATASET_ID = "openproblems_neurips2021/bmmc_cite/normal/log_cp10k"
BASE_URL = (
    "https://openproblems-data.s3.amazonaws.com/"
    "resources/task_predict_modality/datasets/openproblems_neurips2021/bmmc_cite/normal/log_cp10k/"
)


def _is_repo_root(path: Path) -> bool:
    return (path / "frontier_eval").is_dir() and (path / "benchmarks").is_dir()


def _find_repo_root() -> Path:
    if "FRONTIER_ENGINEERING_ROOT" in os.environ:
        return Path(os.environ["FRONTIER_ENGINEERING_ROOT"]).expanduser().resolve()

    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _is_repo_root(parent):
            return parent
    return Path.cwd().resolve()


def _tail(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _truncate_middle(text: str, limit: int = 200_000) -> str:
    if len(text) <= limit:
        return text
    keep = max(0, (limit - 128) // 2)
    omitted = len(text) - (2 * keep)
    return text[:keep] + f"\n\n[... truncated {omitted} chars ...]\n\n" + text[-keep:]


def evaluate(program_path: str, *, repo_root: Path | None = None) -> Any:
    """
    OpenEvolve evaluator for `benchmarks/SingleCellAnalysis/predict_modality`.

    Contract:
    - Runs the candidate program (Python) inside an isolated temp working directory.
    - Candidate must write `prediction.h5ad` in the working directory.
    - Scores against the OpenProblems ground truth using the benchmark verifier.
    """
    start = time.time()
    repo_root = _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    program_path = str(Path(program_path).expanduser().resolve())

    dataset_dir = (
        repo_root
        / "benchmarks"
        / "SingleCellAnalysis"
        / "predict_modality"
        / "resources_cache"
        / "openproblems_neurips2021__bmmc_cite__normal__log_cp10k"
    ).resolve()

    artifacts: dict[str, str] = {}
    artifacts["interface_contract"] = (
        "Hard requirements for candidate program (do NOT change these):\n"
        "1) The evaluator will run: python <program.py> --output prediction.h5ad --dataset-dir <CACHE_DIR>\n"
        "2) Your program MUST accept the flags `--output` and `--dataset-dir` (no additional required CLI args).\n"
        "3) Your program MUST write a valid AnnData file at --output, with:\n"
        "   - layers['normalized'] of shape (n_test_cells, n_mod2_features)\n"
        "   - obs matching test_mod1.obs (same cells/order)\n"
        "   - var matching train_mod2.var (same features/order)\n"
        "   - uns['dataset_id'] present (copied from dataset) and uns['method_id']\n"
        "4) The dataset cache dir already contains or will contain: train_mod1.h5ad, train_mod2.h5ad, "
        "test_mod1.h5ad, test_mod2.h5ad.\n"
        "If you change the CLI interface, the program will fail and receive valid=0."
    )
    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "valid": 0.0,
        "timeout": 0.0,
        "runtime_s": 0.0,
    }

    timeout_s = int(os.environ.get("FRONTIER_EVAL_EVALUATOR_TIMEOUT_S", "1800") or "1800")
    deadline = start + max(1.0, float(timeout_s) - 2.0)  # small margin vs OpenEvolve wait_for()
    dataset_dir.mkdir(parents=True, exist_ok=True)
    truth_path = dataset_dir / "test_mod2.h5ad"
    if truth_path.is_file():
        min_score_reserve_s = min(60, max(10, timeout_s // 5))
    else:
        # First run typically needs to download the ground truth file (can be slow).
        min_score_reserve_s = min(max(60, timeout_s // 2), max(1, timeout_s - 1))
    program_timeout_s = max(1, timeout_s - min_score_reserve_s)

    work_dir = Path(tempfile.mkdtemp(prefix="fe_predict_modality_")).resolve()
    try:
        # 1) Run candidate program
        pred_path = work_dir / "prediction.h5ad"
        env = os.environ.copy()
        env.setdefault("FRONTIER_ENGINEERING_ROOT", str(repo_root))
        env["PYTHONPATH"] = (
            str(repo_root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        )

        cmd = [
            sys.executable,
            program_path,
            "--output",
            str(pred_path),
            "--dataset-dir",
            str(dataset_dir),
        ]

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=max(1, min(program_timeout_s, int(deadline - time.time()))),
                env=env,
            )
        except subprocess.TimeoutExpired as e:
            artifacts["error_message"] = f"program timeout: {e}"
            metrics["timeout"] = 1.0
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        artifacts["program_stdout"] = _tail(proc.stdout)
        artifacts["program_stderr"] = _tail(proc.stderr)
        artifacts["program_stdout_full"] = _truncate_middle(proc.stdout)
        artifacts["program_stderr_full"] = _truncate_middle(proc.stderr)
        metrics["program_returncode"] = float(proc.returncode)

        if proc.returncode != 0:
            artifacts["error_message"] = "candidate program exited non-zero"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        if not pred_path.is_file():
            artifacts["error_message"] = "prediction.h5ad not generated"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        try:
            artifacts["prediction_bytes"] = str(pred_path.stat().st_size)
        except Exception:
            pass

        # 2) Score prediction (subprocess to inherit same dataset cache + enforce timeout)
        try:
            scorer_path = (
                repo_root
                / "benchmarks"
                / "SingleCellAnalysis"
                / "predict_modality"
                / "verification"
                / "evaluate_predict_modality.py"
            ).resolve()
            if not scorer_path.is_file():
                raise FileNotFoundError(f"Scorer not found: {scorer_path}")

            score_cmd = [
                sys.executable,
                str(scorer_path),
                "--prediction",
                str(pred_path),
                "--dataset-dir",
                str(dataset_dir),
            ]
            proc2 = subprocess.run(
                score_cmd,
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=max(1, int(deadline - time.time())),
                env=env,
            )
        except Exception as e:
            artifacts["error_message"] = f"scoring failed: {e}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        artifacts["scoring_stdout"] = _tail(proc2.stdout)
        artifacts["scoring_stderr"] = _tail(proc2.stderr)
        artifacts["scoring_stdout_full"] = _truncate_middle(proc2.stdout)
        artifacts["scoring_stderr_full"] = _truncate_middle(proc2.stderr)
        metrics["scoring_returncode"] = float(proc2.returncode)
        if proc2.returncode != 0:
            artifacts["error_message"] = "scorer exited non-zero"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        try:
            score_metrics = json.loads(proc2.stdout)
        except Exception as e:
            artifacts["error_message"] = f"failed to parse scorer JSON: {e}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        # Merge / normalize
        if isinstance(score_metrics, dict) and "combined_score" in score_metrics:
            try:
                metrics["combined_score"] = float(score_metrics["combined_score"])
            except Exception:
                metrics["combined_score"] = 0.0

        if isinstance(score_metrics, dict):
            metrics["valid"] = float(score_metrics.get("valid", 1.0) or 0.0)

            for key, value in score_metrics.items():
                if key in metrics:
                    continue
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    metrics[key] = float(value)

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
