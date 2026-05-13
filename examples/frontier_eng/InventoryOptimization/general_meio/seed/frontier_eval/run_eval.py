#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except Exception:
            return None
    return None


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: Path, payload: dict[str, Any], *, ensure_ascii: bool) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=ensure_ascii, default=str),
        encoding="utf-8",
    )


def main() -> int:
    benchmark_dir = Path(__file__).resolve().parents[1]

    stdout_path = benchmark_dir / "eval.stdout.txt"
    stderr_path = benchmark_dir / "eval.stderr.txt"
    run_meta_path = benchmark_dir / "run_meta.txt"
    metrics_path = benchmark_dir / "metrics.json"
    artifacts_path = benchmark_dir / "artifacts.json"

    output_dir = benchmark_dir / "output"
    comparison_path = output_dir / "comparison.json"
    baseline_path = output_dir / "baseline_result.json"
    reference_path = output_dir / "reference_result.json"

    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in (
        stdout_path,
        stderr_path,
        run_meta_path,
        metrics_path,
        artifacts_path,
        comparison_path,
        baseline_path,
        reference_path,
    ):
        if stale.is_file():
            stale.unlink()

    start_s = time.time()
    cmd = [sys.executable, "verification/evaluate.py"]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(benchmark_dir),
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        runtime_s = float(time.time() - start_s)
        metrics = {
            "combined_score": 0.0,
            "valid": 0.0,
            "eval_returncode": -1.0,
            "runtime_s": runtime_s,
        }
        artifacts = {
            "benchmark_dir": str(benchmark_dir),
            "candidate_path": os.environ.get("FRONTIER_EVAL_UNIFIED_CANDIDATE_PATH", ""),
            "error_message": f"failed to execute evaluator: {exc}",
            "comparison_json_path": str(comparison_path),
            "baseline_result_json_path": str(baseline_path),
            "reference_result_json_path": str(reference_path),
        }
        _write_json(metrics_path, metrics, ensure_ascii=True)
        _write_json(artifacts_path, artifacts, ensure_ascii=False)
        run_meta_path.write_text(
            "\n".join(
                [
                    f"eval_command={' '.join(cmd)}",
                    "eval_returncode=-1",
                    f"runtime_s={runtime_s:.6f}",
                    f"metrics_json={metrics_path}",
                    f"artifacts_json={artifacts_path}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return 0

    runtime_s = float(time.time() - start_s)
    stdout_path.write_text(proc.stdout, encoding="utf-8", errors="replace")
    stderr_path.write_text(proc.stderr, encoding="utf-8", errors="replace")

    comparison = _read_json(comparison_path)
    candidate_score = None
    reference_score = None
    gap_score = None
    winner = None

    error_message = None
    if comparison is None:
        error_message = "missing or invalid output/comparison.json"
    else:
        candidate_score = _as_float(comparison.get("baseline_final_score"))
        reference_score = _as_float(comparison.get("reference_final_score"))
        gap_score = _as_float(comparison.get("gap_reference_minus_baseline"))
        winner_raw = comparison.get("winner")
        winner = str(winner_raw) if winner_raw is not None else None
        if candidate_score is None:
            error_message = "baseline_final_score is missing in output/comparison.json"

    valid = 1.0 if proc.returncode == 0 and candidate_score is not None else 0.0
    combined_score = float(candidate_score) if valid > 0 else 0.0

    metrics: dict[str, float] = {
        "combined_score": combined_score,
        "valid": valid,
        "eval_returncode": float(proc.returncode),
        "runtime_s": runtime_s,
    }
    if candidate_score is not None:
        metrics["candidate_score"] = float(candidate_score)
    if reference_score is not None:
        metrics["reference_score"] = float(reference_score)
    if gap_score is not None:
        metrics["gap_to_reference"] = float(gap_score)

    artifacts: dict[str, Any] = {
        "benchmark_dir": str(benchmark_dir),
        "candidate_path": os.environ.get("FRONTIER_EVAL_UNIFIED_CANDIDATE_PATH", ""),
        "eval_command": " ".join(cmd),
        "eval_returncode": proc.returncode,
        "runtime_s": runtime_s,
        "comparison_json_path": str(comparison_path),
        "baseline_result_json_path": str(baseline_path),
        "reference_result_json_path": str(reference_path),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    if winner is not None:
        artifacts["winner"] = winner

    if proc.returncode != 0:
        stderr_tail = (proc.stderr or "")[-1200:]
        artifacts["error_message"] = (
            f"verification/evaluate.py returned non-zero exit code {proc.returncode}"
        )
        if stderr_tail:
            artifacts["stderr_tail"] = stderr_tail
    elif error_message:
        artifacts["error_message"] = error_message

    _write_json(metrics_path, metrics, ensure_ascii=True)
    _write_json(artifacts_path, artifacts, ensure_ascii=False)

    run_meta_path.write_text(
        "\n".join(
            [
                f"eval_command={' '.join(cmd)}",
                f"eval_returncode={proc.returncode}",
                f"runtime_s={runtime_s:.6f}",
                f"metrics_json={metrics_path}",
                f"artifacts_json={artifacts_path}",
                f"comparison_json={comparison_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
