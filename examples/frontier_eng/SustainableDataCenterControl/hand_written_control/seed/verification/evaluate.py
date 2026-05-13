from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BENCHMARK_DIR = Path(__file__).resolve().parents[1]

if str(BENCHMARK_DIR) not in sys.path:
    sys.path.insert(0, str(BENCHMARK_DIR))

from benchmark_core import (
    format_report,
    load_policy_module,
    resolve_sustaindc_root,
    run_benchmark,
)


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(BENCHMARK_DIR).as_posix()
    except ValueError:
        return resolved.as_posix()


def _write_json(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _build_metrics(report: dict[str, Any]) -> dict[str, float]:
    candidate = report["candidate_aggregate"]
    noop = report["noop_aggregate"]
    average_score = float(report["average_score"])
    score_ceiling = float(report["score_ceiling"])
    return {
        "valid": 1.0,
        "combined_score": average_score,
        "average_score": average_score,
        "score_fraction": average_score / score_ceiling if score_ceiling else 0.0,
        "score_ceiling": score_ceiling,
        "num_scenarios": float(len(report["scenario_reports"])),
        "steps_total": float(candidate["steps"]),
        "candidate_carbon_kg": float(candidate["carbon_kg"]),
        "candidate_water_l": float(candidate["water_l"]),
        "candidate_dropped_tasks": float(candidate["dropped_tasks"]),
        "candidate_overdue_tasks": float(candidate["overdue_tasks"]),
        "noop_carbon_kg": float(noop["carbon_kg"]),
        "noop_water_l": float(noop["water_l"]),
        "noop_dropped_tasks": float(noop["dropped_tasks"]),
        "noop_overdue_tasks": float(noop["overdue_tasks"]),
    }


def _build_artifacts(report: dict[str, Any]) -> dict[str, Any]:
    scenario_scores = {
        item["scenario"]["name"]: item["score_breakdown"]["score"]
        for item in report["scenario_reports"]
    }
    return {
        "solution_path": report["solution_path"],
        "sustaindc_root": report["sustaindc_root"],
        "scenario_scores": scenario_scores,
        "report": report,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate a hand-written SustainDC control policy."
    )
    parser.add_argument(
        "--solution",
        type=Path,
        default=BENCHMARK_DIR / "baseline" / "solution.py",
        help="Path to the Python file that defines decide_actions(observations).",
    )
    parser.add_argument(
        "--save-json",
        type=Path,
        default=Path(__file__).resolve().with_name("last_eval.json"),
        help="Where to save the structured evaluation report.",
    )
    parser.add_argument(
        "--sustaindc-root",
        type=Path,
        default=None,
        help="Path to the sibling dc-rl checkout. Defaults to ./sustaindc.",
    )
    parser.add_argument(
        "--metrics-out",
        type=Path,
        default=None,
        help="Optional path to write unified-task metrics as JSON.",
    )
    parser.add_argument(
        "--artifacts-out",
        type=Path,
        default=None,
        help="Optional path to write unified-task artifacts as JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    solution_path = args.solution.resolve()
    if not solution_path.exists():
        raise FileNotFoundError(f"Solution file not found: {solution_path}")

    policy_module = load_policy_module(solution_path)
    sustaindc_root = resolve_sustaindc_root(args.sustaindc_root)
    report = run_benchmark(policy_module, sustaindc_root=sustaindc_root)
    report["solution_path"] = _display_path(solution_path)
    report["sustaindc_root"] = _display_path(sustaindc_root)

    print(format_report(report))

    _write_json(args.save_json, report)
    _write_json(args.metrics_out, _build_metrics(report))
    _write_json(args.artifacts_out, _build_artifacts(report))
    print()
    print(f"Structured report saved to: {args.save_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
