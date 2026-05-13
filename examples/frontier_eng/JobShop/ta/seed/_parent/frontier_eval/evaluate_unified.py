from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import statistics
import sys
import time
import traceback
from pathlib import Path
from types import ModuleType
from typing import Any


def _load_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _score(target: int | None, makespan: int | None) -> float | None:
    if target is None or makespan is None or makespan <= 0:
        return None
    return min(100.0, 100.0 * float(target) / float(makespan))


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.fmean(values))


def _to_float(value: float | None, *, default: float = 0.0) -> float:
    if value is None:
        return default
    return float(value)


def _parse_env_int(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    return int(raw)


def _parse_env_float(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    return float(raw)


def _parse_env_instances(name: str) -> list[str] | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    items = [part.strip() for part in raw.replace(",", " ").split()]
    picked = [item for item in items if item]
    return picked or None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _capture_report(eval_mod: ModuleType, results: list[Any]) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        eval_mod.print_report(results)
    return buf.getvalue()


def _compute_metrics(results: list[Any]) -> dict[str, float]:
    baseline_best_scores: list[float] = []
    reference_best_scores: list[float] = []
    baseline_lb_scores: list[float] = []
    reference_lb_scores: list[float] = []
    baseline_opt_gaps: list[float] = []
    reference_opt_gaps: list[float] = []
    baseline_runtime_s: list[float] = []
    reference_runtime_s: list[float] = []

    baseline_failures = 0
    reference_failures = 0
    for row in results:
        target = row.optimum if row.optimum is not None else row.upper_bound
        b_best = _score(target, row.baseline_makespan)
        r_best = _score(target, row.reference_makespan)
        b_lb = _score(row.lower_bound, row.baseline_makespan)
        r_lb = _score(row.lower_bound, row.reference_makespan)

        if b_best is not None:
            baseline_best_scores.append(b_best)
        if r_best is not None:
            reference_best_scores.append(r_best)
        if b_lb is not None:
            baseline_lb_scores.append(b_lb)
        if r_lb is not None:
            reference_lb_scores.append(r_lb)

        if (
            row.optimum is not None
            and row.optimum > 0
            and row.baseline_makespan is not None
        ):
            baseline_opt_gaps.append(
                100.0 * (float(row.baseline_makespan) - float(row.optimum)) / float(row.optimum)
            )
        if row.optimum is not None and row.optimum > 0 and row.reference_makespan is not None:
            reference_opt_gaps.append(
                100.0 * (float(row.reference_makespan) - float(row.optimum)) / float(row.optimum)
            )

        baseline_runtime_s.append(float(row.baseline_elapsed_s))
        if row.reference_elapsed_s is not None:
            reference_runtime_s.append(float(row.reference_elapsed_s))
        if not bool(getattr(row, "baseline_valid", row.baseline_makespan is not None)):
            baseline_failures += 1
        if row.reference_error is not None:
            reference_failures += 1

    instances = len(results)
    baseline_successes = max(instances - baseline_failures, 0)
    reference_successes = max(instances - reference_failures, 0)
    baseline_success_rate = (
        float(baseline_successes) / float(instances) if instances > 0 else 0.0
    )
    reference_success_rate = (
        float(reference_successes) / float(instances) if instances > 0 else 0.0
    )

    score_best_avg_baseline = _to_float(_mean(baseline_best_scores))
    valid = 1.0 if instances > 0 and baseline_failures == 0 else 0.0

    return {
        "instances": float(instances),
        "baseline_failures": float(baseline_failures),
        "baseline_successes": float(baseline_successes),
        "baseline_success_rate": baseline_success_rate,
        "reference_failures": float(reference_failures),
        "reference_successes": float(reference_successes),
        "reference_success_rate": reference_success_rate,
        "score_best_avg_baseline": score_best_avg_baseline,
        "score_best_avg_reference": _to_float(_mean(reference_best_scores)),
        "score_lb_avg_baseline": _to_float(_mean(baseline_lb_scores)),
        "score_lb_avg_reference": _to_float(_mean(reference_lb_scores)),
        "optimality_gap_avg_baseline": _to_float(_mean(baseline_opt_gaps)),
        "optimality_gap_avg_reference": _to_float(_mean(reference_opt_gaps)),
        "baseline_runtime_avg_s": _to_float(_mean(baseline_runtime_s)),
        "reference_runtime_avg_s": _to_float(_mean(reference_runtime_s)),
        "combined_score": score_best_avg_baseline if valid > 0.0 else 0.0,
        "valid": valid,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified evaluator entrypoint for JobShop family subtasks."
    )
    parser.add_argument("--benchmark-dir", required=True, help="Benchmark family directory path.")
    parser.add_argument("--candidate", default="", help="Candidate file path from unified evaluator.")
    parser.add_argument("--metrics-out", default="", help="Path to write metrics.json.")
    parser.add_argument("--artifacts-out", default="", help="Path to write artifacts.json.")
    parser.add_argument("--stdout-log", default="", help="Path to write evaluation report text.")
    parser.add_argument("--stderr-log", default="", help="Path to write error details.")
    parser.add_argument(
        "--max-instances",
        type=int,
        default=None,
        help="Override max number of instances (defaults to JOBSHOP_EVAL_MAX_INSTANCES).",
    )
    parser.add_argument(
        "--reference-time-limit",
        type=float,
        default=None,
        help="Reference solver time limit per instance in seconds (default 10.0).",
    )
    parser.add_argument(
        "--instances",
        nargs="*",
        default=None,
        help="Optional explicit instance names (defaults to JOBSHOP_EVAL_INSTANCES).",
    )
    args = parser.parse_args()

    benchmark_dir = Path(args.benchmark_dir).resolve()
    family = benchmark_dir.name
    vendored_json = (Path(__file__).resolve().parents[1] / "data" / "benchmark_instances.json").resolve()
    if vendored_json.is_file():
        # Ensure baseline/init.py can locate vendored benchmark data in unified sandbox runs.
        os.environ.setdefault("JOBSHOP_BENCHMARK_JSON", str(vendored_json))
    metrics_out = Path(args.metrics_out).resolve() if args.metrics_out else (benchmark_dir / "metrics.json")
    artifacts_out = (
        Path(args.artifacts_out).resolve() if args.artifacts_out else (benchmark_dir / "artifacts.json")
    )
    stdout_log = (
        Path(args.stdout_log).resolve() if args.stdout_log else (benchmark_dir / "eval.stdout.txt")
    )
    stderr_log = (
        Path(args.stderr_log).resolve() if args.stderr_log else (benchmark_dir / "eval.stderr.txt")
    )

    max_instances = args.max_instances
    if max_instances is None:
        max_instances = _parse_env_int("JOBSHOP_EVAL_MAX_INSTANCES")

    reference_time_limit = args.reference_time_limit
    if reference_time_limit is None:
        reference_time_limit = _parse_env_float("JOBSHOP_REFERENCE_TIME_LIMIT")
    if reference_time_limit is None:
        reference_time_limit = 10.0

    instances = args.instances
    if instances is None:
        instances = _parse_env_instances("JOBSHOP_EVAL_INSTANCES")

    t0 = time.perf_counter()
    artifacts: dict[str, Any] = {
        "family": family,
        "benchmark_dir": str(benchmark_dir),
        "candidate_path": args.candidate,
        "reference_time_limit_s": float(reference_time_limit),
        "max_instances": max_instances,
        "instances_filter": instances,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
    }

    try:
        eval_mod = _load_module(f"jobshop_eval_{family}", benchmark_dir / "verification" / "evaluate.py")
        baseline_mod = eval_mod._load_module(
            f"jobshop_baseline_{family}", benchmark_dir / "baseline" / "init.py"
        )
        reference_mod = eval_mod._load_module(
            f"jobshop_reference_{family}", benchmark_dir / "verification" / "reference.py"
        )

        all_instances = baseline_mod.load_family_instances()
        selected = eval_mod._select_instances(all_instances, instances, max_instances)
        artifacts["selected_instances"] = [ins["name"] for ins in selected]

        results = eval_mod.evaluate_instances(
            selected,
            float(reference_time_limit),
            baseline_mod,
            reference_mod,
        )
        report_text = _capture_report(eval_mod, results)
        stdout_log.parent.mkdir(parents=True, exist_ok=True)
        stdout_log.write_text(report_text, encoding="utf-8")
        print(report_text, end="")

        metrics = _compute_metrics(results)
        metrics["evaluation_wall_time_s"] = float(time.perf_counter() - t0)
        metrics["reference_time_limit_s"] = float(reference_time_limit)
        if max_instances is not None:
            metrics["max_instances"] = float(max_instances)

        baseline_errors: list[dict[str, str]] = []
        reference_errors: list[dict[str, str]] = []
        for row in results:
            if not bool(getattr(row, "baseline_valid", row.baseline_makespan is not None)):
                baseline_errors.append(
                    {
                        "instance": row.name,
                        "error": str(getattr(row, "baseline_note", "invalid baseline schedule")),
                    }
                )
            if row.reference_error is None:
                continue
            reference_errors.append({"instance": row.name, "error": row.reference_error})
        artifacts["baseline_errors"] = baseline_errors
        artifacts["reference_errors"] = reference_errors
        artifacts["report"] = report_text
        artifacts["evaluation_wall_time_s"] = metrics["evaluation_wall_time_s"]

        stderr_log.parent.mkdir(parents=True, exist_ok=True)
        stderr_log.write_text("", encoding="utf-8")

        _write_json(metrics_out, metrics)
        _write_json(artifacts_out, artifacts)
        return 0
    except Exception:
        error_text = traceback.format_exc()
        stderr_log.parent.mkdir(parents=True, exist_ok=True)
        stderr_log.write_text(error_text, encoding="utf-8")
        print(error_text, file=sys.stderr)

        metrics = {
            "combined_score": 0.0,
            "valid": 0.0,
            "evaluation_error": 1.0,
            "evaluation_wall_time_s": float(time.perf_counter() - t0),
            "reference_time_limit_s": float(reference_time_limit),
        }
        if max_instances is not None:
            metrics["max_instances"] = float(max_instances)
        artifacts["error_message"] = "JobShop unified evaluation failed before completion."
        artifacts["traceback"] = error_text
        artifacts["evaluation_wall_time_s"] = metrics["evaluation_wall_time_s"]

        _write_json(metrics_out, metrics)
        _write_json(artifacts_out, artifacts)
        # Keep return code 0 so unified can read metrics/artifacts written above.
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
