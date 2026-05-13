from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import json
import shutil
from pathlib import Path

def _is_repo_root(path: Path) -> bool:
    if not (path / "frontier_eval").is_dir():
        return False
    return (path / "benchmarks").is_dir()

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

def evaluate(program_path: str, *, repo_root: Path | None = None):
    """
    Evaluator for benchmarks/ParticlePhysics/MuonTomography.
    - Runs candidate program (Python) to generate `solution.json`
    - Runs Python validator `evaluator.py`
    - Parses output JSON for pass/fail and score
    """
    start = time.time()
    repo_root = _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    program_path = Path(program_path).expanduser().resolve()

    work_dir = Path(tempfile.mkdtemp(prefix="fe_muon_")).resolve()
    artifacts: dict[str, str] = {}
    output_candidates = [work_dir / "solution.json", program_path.parent / "solution.json"]
    output_mtimes: dict[Path, int | None] = {}

    for path in output_candidates:
        try:
            output_mtimes[path] = path.stat().st_mtime_ns if path.exists() else None
        except OSError:
            output_mtimes[path] = None

    try:
        # ==========================================
        # 1) generate solution.json
        # ==========================================
        try:
            proc = subprocess.run(
                [sys.executable, str(program_path)],
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired as e:
            metrics = {
                "combined_score": 0.0,
                "valid": 0.0,
                "timeout": 1.0,
                "runtime_s": float(time.time() - start),
            }
            artifacts["error_message"] = f"program timeout: {e}"
            return _wrap(metrics, artifacts)

        artifacts["program_stdout"] = _tail(proc.stdout)
        artifacts["program_stderr"] = _tail(proc.stderr)
        metrics: dict[str, float] = {
            "combined_score": 0.0,
            "valid": 0.0,
            "timeout": 0.0,
            "runtime_s": 0.0,
        }
        metrics["program_returncode"] = float(proc.returncode)

        results_path: Path | None = None
        for candidate in output_candidates:
            try:
                if not candidate.exists():
                    continue
                previous_mtime = output_mtimes.get(candidate)
                current_mtime = candidate.stat().st_mtime_ns
                if previous_mtime is None or current_mtime != previous_mtime:
                    results_path = candidate
                    break
            except OSError:
                continue

        if results_path is None:
            artifacts["error_message"] = "solution.json not generated"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        artifacts["solution.json"] = results_path.read_text(encoding="utf-8", errors="replace")

        # ==========================================
        # 2) run evaluator.py
        # ==========================================
        eval_script = (repo_root / "benchmarks" / "ParticlePhysics" / "MuonTomography" / "verification" / "evaluator.py").resolve()
        
        try:
            proc2 = subprocess.run(
                [sys.executable, str(eval_script), str(results_path)],
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired as e:
            artifacts["error_message"] = f"evaluator timeout: {e}"
            metrics["timeout"] = 1.0
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        artifacts["evaluator_stdout"] = _tail(proc2.stdout)
        artifacts["evaluator_stderr"] = _tail(proc2.stderr)

       
        score = 0.0
        passed = False
        try:
            
            output_lines = proc2.stdout.strip().split('\n')
            eval_result = json.loads(output_lines[-1])
            
            if eval_result.get("status") == "success":
                score = float(eval_result.get("score", 0.0))
                passed = score > 0.0
            else:
                artifacts["error_message"] = eval_result.get("message", "Evaluation failed")
        except Exception as e:
            artifacts["error_message"] = f"Failed to parse evaluator JSON output: {e}"

        metrics["runtime_s"] = float(time.time() - start)
        metrics["combined_score"] = float(score)
        metrics["valid"] = 1.0 if passed else 0.0

        return _wrap(metrics, artifacts)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

def _wrap(metrics: dict[str, float], artifacts: dict[str, str]):
    try:
        from openevolve.evaluation_result import EvaluationResult
    except Exception:
        return {"metrics": metrics, "artifacts": artifacts}
    return EvaluationResult(metrics=metrics, artifacts=artifacts)
