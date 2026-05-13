#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _maybe_float(value: Any) -> float | None:
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
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any], *, ensure_ascii: bool) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=ensure_ascii, default=str),
        encoding="utf-8",
    )


def _extract_metrics(result_payload: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    metrics: dict[str, float] = {}
    non_numeric: dict[str, Any] = {}
    for key, value in result_payload.items():
        metric_value = _maybe_float(value)
        if metric_value is None:
            non_numeric[str(key)] = value
            continue
        metrics[str(key)] = float(metric_value)

    score_value = metrics.get("score")
    valid_value = metrics.get("valid", 1.0)
    if score_value is not None:
        metrics["combined_score"] = float(score_value) if valid_value > 0 else 0.0
    elif "combined_score" not in metrics:
        metrics["combined_score"] = 1.0 if valid_value > 0 else 0.0
    return metrics, non_numeric


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")


def main() -> int:
    benchmark_dir = Path(
        os.environ.get("FRONTIER_EVAL_UNIFIED_BENCHMARK_DIR", os.getcwd())
    ).resolve()
    source_benchmark_dir = Path(
        os.environ.get("FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR", benchmark_dir)
    ).resolve()
    candidate_path = Path(
        os.environ.get(
            "FRONTIER_EVAL_UNIFIED_CANDIDATE_PATH",
            str(benchmark_dir / "baseline" / "init.py"),
        )
    ).resolve()

    raw_task_path = benchmark_dir / "data" / "raw_task.json"
    outputs_dir = benchmark_dir / "outputs"
    prepared_path = outputs_dir / "prepared.json"
    solution_path = outputs_dir / "solution.json"
    result_path = outputs_dir / "result.json"

    logs_dir = benchmark_dir / "frontier_eval_logs"
    metrics_path = benchmark_dir / "metrics.json"
    artifacts_path = benchmark_dir / "artifacts.json"
    run_meta_path = benchmark_dir / "run_meta.txt"

    if outputs_dir.exists():
        shutil.rmtree(outputs_dir)
    if logs_dir.exists():
        shutil.rmtree(logs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    for stale_path in (metrics_path, artifacts_path, run_meta_path):
        if stale_path.exists():
            stale_path.unlink()

    start_s = time.time()
    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "valid": 0.0,
    }
    artifacts: dict[str, Any] = {
        "benchmark_dir": str(benchmark_dir),
        "source_benchmark_dir": str(source_benchmark_dir),
        "candidate_path": str(candidate_path),
        "raw_task_path": str(raw_task_path),
        "prepared_path": str(prepared_path),
        "solution_path": str(solution_path),
        "result_path": str(result_path),
    }

    stage_commands = [
        (
            "prepare",
            [
                sys.executable,
                "verification/evaluate.py",
                "prepare",
                "--raw-task",
                "data/raw_task.json",
                "--prepared-output",
                "outputs/prepared.json",
            ],
        ),
        (
            "solve",
            [
                sys.executable,
                str(candidate_path),
                "--prepared-input",
                str(prepared_path),
                "--solution-output",
                str(solution_path),
            ],
        ),
        (
            "evaluate",
            [
                sys.executable,
                "verification/evaluate.py",
                "evaluate",
                "--prepared-input",
                "outputs/prepared.json",
                "--solution",
                "outputs/solution.json",
                "--result-output",
                "outputs/result.json",
            ],
        ),
    ]

    run_meta_lines: list[str] = []
    failed_stage: str | None = None

    try:
        for stage_name, command in stage_commands:
            stage_start_s = time.time()
            artifacts[f"{stage_name}_command"] = " ".join(command)
            try:
                proc = subprocess.run(
                    command,
                    cwd=str(benchmark_dir),
                    capture_output=True,
                    text=True,
                )
            except Exception as exc:
                failed_stage = stage_name
                metrics[f"{stage_name}_runtime_s"] = float(time.time() - stage_start_s)
                artifacts["error_message"] = f"{stage_name} stage failed to start: {exc}"
                run_meta_lines.append(f"{stage_name}_exception={exc}")
                break

            stage_runtime_s = float(time.time() - stage_start_s)
            stdout_path = logs_dir / f"{stage_name}.stdout.txt"
            stderr_path = logs_dir / f"{stage_name}.stderr.txt"
            _write_text(stdout_path, proc.stdout)
            _write_text(stderr_path, proc.stderr)

            metrics[f"{stage_name}_returncode"] = float(proc.returncode)
            metrics[f"{stage_name}_runtime_s"] = stage_runtime_s
            artifacts[f"{stage_name}_stdout_path"] = str(stdout_path)
            artifacts[f"{stage_name}_stderr_path"] = str(stderr_path)

            run_meta_lines.extend(
                [
                    f"{stage_name}_command={' '.join(command)}",
                    f"{stage_name}_returncode={proc.returncode}",
                    f"{stage_name}_runtime_s={stage_runtime_s:.6f}",
                    f"{stage_name}_stdout={stdout_path}",
                    f"{stage_name}_stderr={stderr_path}",
                ]
            )

            if proc.returncode != 0:
                failed_stage = stage_name
                artifacts["error_message"] = (
                    f"{stage_name} stage returned non-zero exit code {proc.returncode}"
                )
                break

        result_payload = _read_json(result_path)
        if failed_stage is None:
            if result_payload is None:
                failed_stage = "result"
                artifacts["error_message"] = "missing or invalid outputs/result.json"
            else:
                result_metrics, non_numeric_result = _extract_metrics(result_payload)
                metrics.update(result_metrics)
                if result_metrics.get("valid", 0.0) > 0:
                    metrics["valid"] = result_metrics["valid"]
                if non_numeric_result:
                    artifacts["result_non_numeric"] = non_numeric_result
                artifacts["result_payload"] = result_payload

        if failed_stage is not None:
            metrics["valid"] = 0.0
            metrics["combined_score"] = 0.0
            artifacts["failed_stage"] = failed_stage

    except Exception as exc:
        metrics["valid"] = 0.0
        metrics["combined_score"] = 0.0
        artifacts["error_message"] = f"unexpected wrapper failure: {exc}"

    metrics["wrapper_runtime_s"] = float(time.time() - start_s)

    _write_json(metrics_path, metrics, ensure_ascii=True)
    _write_json(artifacts_path, artifacts, ensure_ascii=False)

    run_meta_lines.extend(
        [
            f"metrics_json={metrics_path}",
            f"artifacts_json={artifacts_path}",
            f"wrapper_runtime_s={metrics['wrapper_runtime_s']:.6f}",
        ]
    )
    _write_text(run_meta_path, "\n".join(run_meta_lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
