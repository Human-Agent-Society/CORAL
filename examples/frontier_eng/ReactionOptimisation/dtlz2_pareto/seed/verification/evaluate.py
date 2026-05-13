"""Evaluate baseline and reference solutions for the DTLZ2 task."""

from __future__ import annotations

import argparse
import math
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def _is_repo_root(path: Path) -> bool:
    return (path / "benchmarks").is_dir() and (path / "frontier_eval").is_dir()


def _ensure_domain_on_path() -> None:
    env_root = (os.environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    candidates: list[Path] = []
    if env_root:
        candidates.append(Path(env_root).expanduser().resolve())

    here = Path(__file__).resolve()
    candidates.extend([here.parent, *here.parents])

    repo_root = next((path for path in candidates if _is_repo_root(path)), None)
    if repo_root is None:
        raise RuntimeError("Could not locate repository root for ReactionOptimisation.")

    domain_root = repo_root / "benchmarks" / "ReactionOptimisation"
    if not domain_root.is_dir():
        raise RuntimeError(f"ReactionOptimisation directory not found under {repo_root}.")

    domain_root_str = str(domain_root)
    if domain_root_str not in sys.path:
        sys.path.insert(0, domain_root_str)


_ensure_domain_on_path()

from dtlz2_pareto import task
from dtlz2_pareto.verification.reference import solve as solve_reference
from shared.cli import load_module, write_json
from shared.utils import dump_json, score_summary

DEFAULT_CANDIDATE_PATH = Path(__file__).resolve().parents[1] / "baseline" / "solution.py"
INTEGER_TOL = 1e-6
FLOAT_REL_TOL = 1e-9
FLOAT_ABS_TOL = 1e-9


class CandidateValidationError(RuntimeError):
    """Raised when a candidate submission violates the task contract."""


class BudgetExceededError(CandidateValidationError):
    """Raised when a candidate exceeds the declared evaluation budget."""


class _ExperimentBudgetProxy:
    """Wrap a Summit experiment so the evaluator owns budget accounting."""

    def __init__(self, inner: Any, tracker: dict[str, int]):
        self._inner = inner
        self._tracker = tracker

    def run_experiments(self, *args, **kwargs):
        return self._inner.run_experiments(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


@contextmanager
def _instrument_summit_budget(tracker_ref: dict[str, dict[str, int] | None]):
    from summit.experiment import Experiment

    original_run_experiments = Experiment.run_experiments

    def _tracked_run_experiments(self, conditions, *args, **kwargs):
        tracker = tracker_ref["active"]
        if tracker is not None:
            try:
                batch_evals = max(1, int(len(conditions)))
            except Exception:
                batch_evals = 1
            tracker["calls"] += batch_evals
            if tracker["calls"] > tracker["budget"]:
                raise BudgetExceededError(
                    f"evaluation budget exceeded: {tracker['calls']} > {tracker['budget']}"
                )
        return original_run_experiments(self, conditions, *args, **kwargs)

    Experiment.run_experiments = _tracked_run_experiments
    try:
        yield
    finally:
        Experiment.run_experiments = original_run_experiments


def _coerce_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise CandidateValidationError(f"{field_name} must be an integer, got bool")
    try:
        numeric = float(value)
    except Exception as exc:
        raise CandidateValidationError(f"{field_name} must be numeric") from exc
    if not math.isfinite(numeric):
        raise CandidateValidationError(f"{field_name} must be finite")
    rounded = int(round(numeric))
    if abs(numeric - rounded) > INTEGER_TOL:
        raise CandidateValidationError(f"{field_name} must be an integer")
    return rounded


def _coerce_float(value: Any, field_name: str) -> float:
    try:
        numeric = float(value)
    except Exception as exc:
        raise CandidateValidationError(f"{field_name} must be numeric") from exc
    if not math.isfinite(numeric):
        raise CandidateValidationError(f"{field_name} must be finite")
    return numeric


def _normalize_history(history: Any, budget: int) -> list[dict[str, Any]]:
    if not isinstance(history, list):
        raise CandidateValidationError("history must be a list")
    if len(history) > budget:
        raise CandidateValidationError(
            f"history length exceeds budget: {len(history)} > {budget}"
        )

    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(history):
        if not isinstance(row, dict):
            raise CandidateValidationError(f"history[{index}] must be a dict")

        normalized_row = dict(row)
        for key in task.INPUT_NAMES:
            if key not in row:
                raise CandidateValidationError(f"history[{index}] missing input field {key}")
            value = _coerce_float(row[key], f"history[{index}].{key}")
            if not 0.0 <= value <= 1.0:
                raise CandidateValidationError(
                    f"history[{index}].{key} must lie in [0, 1], got {value}"
                )
            normalized_row[key] = value

        for key in task.OBJECTIVE_NAMES:
            if key not in row:
                raise CandidateValidationError(f"history[{index}] missing objective field {key}")
            normalized_row[key] = _coerce_float(row[key], f"history[{index}].{key}")

        normalized.append(normalized_row)

    return normalized


def _validate_summary(summary: Any, expected: dict[str, Any]) -> None:
    if not isinstance(summary, dict):
        raise CandidateValidationError("summary must be a dict")

    for key, expected_value in expected.items():
        if key not in summary:
            raise CandidateValidationError(f"summary missing field {key}")
        actual_value = summary[key]
        if isinstance(expected_value, int):
            if _coerce_int(actual_value, f"summary.{key}") != expected_value:
                raise CandidateValidationError(
                    f"summary.{key} does not match recomputed value {expected_value}"
                )
            continue

        actual_float = _coerce_float(actual_value, f"summary.{key}")
        if not math.isclose(
            actual_float,
            float(expected_value),
            rel_tol=FLOAT_REL_TOL,
            abs_tol=FLOAT_ABS_TOL,
        ):
            raise CandidateValidationError(
                f"summary.{key} does not match recomputed value {expected_value}"
            )


def _normalize_run(
    run: Any,
    *,
    seed: int,
    budget: int,
    actual_evaluations: int,
    fallback_algorithm_name: str,
) -> dict[str, Any]:
    if not isinstance(run, dict):
        raise CandidateValidationError("solve() must return a dict")

    if "task_name" in run and run["task_name"] != task.TASK_NAME:
        raise CandidateValidationError(
            f"task_name mismatch: expected {task.TASK_NAME}, got {run['task_name']}"
        )
    if "seed" in run and _coerce_int(run["seed"], "seed") != seed:
        raise CandidateValidationError(f"reported seed does not match evaluator seed {seed}")
    if "budget" in run and _coerce_int(run["budget"], "budget") != budget:
        raise CandidateValidationError(
            f"reported budget does not match evaluator budget {budget}"
        )

    history = _normalize_history(run.get("history"), budget)
    if actual_evaluations != len(history):
        raise CandidateValidationError(
            "reported history length does not match actual benchmark evaluations: "
            f"{len(history)} != {actual_evaluations}"
        )

    recomputed_summary = task.summarize(history)
    _validate_summary(run.get("summary"), recomputed_summary)

    algorithm_name = run.get("algorithm_name", fallback_algorithm_name)
    if not isinstance(algorithm_name, str) or not algorithm_name.strip():
        algorithm_name = fallback_algorithm_name

    return {
        "task_name": task.TASK_NAME,
        "algorithm_name": algorithm_name,
        "seed": seed,
        "budget": budget,
        "history": history,
        "summary": recomputed_summary,
        "validation": {
            "is_valid": True,
            "actual_evaluations": actual_evaluations,
            "reported_history_length": len(history),
        },
    }


def _invalid_run(
    *,
    seed: int,
    budget: int,
    reason: str,
    fallback_algorithm_name: str,
    actual_evaluations: int,
    reported_history_length: int | None = None,
) -> dict[str, Any]:
    return {
        "task_name": task.TASK_NAME,
        "algorithm_name": fallback_algorithm_name,
        "seed": seed,
        "budget": budget,
        "history": [],
        "summary": task.summarize([]),
        "validation": {
            "is_valid": False,
            "reason": reason,
            "actual_evaluations": actual_evaluations,
            "reported_history_length": reported_history_length,
        },
    }


def _run_candidate_with_validation(
    solve_fn,
    *,
    seed: int,
    budget: int,
    tracker_ref: dict[str, dict[str, int] | None],
    fallback_algorithm_name: str,
) -> dict[str, Any]:
    tracker = {"calls": 0, "budget": budget}
    tracker_ref["active"] = tracker
    raw_run: Any = None
    try:
        raw_run = solve_fn(seed=seed, budget=budget)
    except Exception as exc:
        return _invalid_run(
            seed=seed,
            budget=budget,
            reason=str(exc),
            fallback_algorithm_name=fallback_algorithm_name,
            actual_evaluations=tracker["calls"],
        )
    finally:
        tracker_ref["active"] = None

    reported_history_length = None
    algorithm_name = fallback_algorithm_name
    if isinstance(raw_run, dict):
        history = raw_run.get("history")
        if isinstance(history, list):
            reported_history_length = len(history)
        if isinstance(raw_run.get("algorithm_name"), str) and raw_run["algorithm_name"].strip():
            algorithm_name = raw_run["algorithm_name"]

    try:
        return _normalize_run(
            raw_run,
            seed=seed,
            budget=budget,
            actual_evaluations=tracker["calls"],
            fallback_algorithm_name=algorithm_name,
        )
    except CandidateValidationError as exc:
        return _invalid_run(
            seed=seed,
            budget=budget,
            reason=str(exc),
            fallback_algorithm_name=algorithm_name,
            actual_evaluations=tracker["calls"],
            reported_history_length=reported_history_length,
        )


def _run_reference_with_validation(
    solve_fn,
    *,
    seed: int,
    budget: int,
    tracker_ref: dict[str, dict[str, int] | None],
    fallback_algorithm_name: str,
) -> dict[str, Any]:
    tracker = {"calls": 0, "budget": budget}
    tracker_ref["active"] = tracker
    try:
        raw_run = solve_fn(seed=seed, budget=budget)
    finally:
        tracker_ref["active"] = None

    return _normalize_run(
        raw_run,
        seed=seed,
        budget=budget,
        actual_evaluations=tracker["calls"],
        fallback_algorithm_name=fallback_algorithm_name,
    )


def evaluate(candidate_path: Path, seeds: list[int], budget: int) -> dict:
    tracker_ref: dict[str, dict[str, int] | None] = {"active": None}
    original_create_benchmark = task.create_benchmark

    def _instrumented_create_benchmark():
        experiment = original_create_benchmark()
        tracker = tracker_ref["active"]
        if tracker is None:
            return experiment
        return _ExperimentBudgetProxy(experiment, tracker)

    task.create_benchmark = _instrumented_create_benchmark
    try:
        with _instrument_summit_budget(tracker_ref):
            candidate_module = load_module(candidate_path, f"{task.TASK_NAME}_candidate")
            solve_candidate = getattr(candidate_module, "solve", None)
            if not callable(solve_candidate):
                raise AttributeError(f"{candidate_path} does not define a callable `solve`.")

            baseline_runs = []
            reference_runs = []
            for seed in seeds:
                baseline_runs.append(
                    _run_candidate_with_validation(
                        solve_candidate,
                        seed=seed,
                        budget=budget,
                        tracker_ref=tracker_ref,
                        fallback_algorithm_name="invalid_candidate",
                    )
                )
                reference_runs.append(
                    _run_reference_with_validation(
                        solve_reference,
                        seed=seed,
                        budget=budget,
                        tracker_ref=tracker_ref,
                        fallback_algorithm_name="reference",
                    )
                )
    finally:
        task.create_benchmark = original_create_benchmark

    baseline_scores = [run["summary"]["score"] for run in baseline_runs]
    reference_scores = [run["summary"]["score"] for run in reference_runs]
    invalid_candidate_runs = [
        run["validation"] for run in baseline_runs if not run["validation"]["is_valid"]
    ]
    result = {
        "task_name": task.TASK_NAME,
        "candidate_path": str(candidate_path),
        "budget": budget,
        "seeds": seeds,
        "baseline": {
            "algorithm_name": baseline_runs[0]["algorithm_name"],
            "scores": baseline_scores,
            "aggregate": score_summary(baseline_scores),
            "runs": baseline_runs,
            "validation": {
                "all_valid": len(invalid_candidate_runs) == 0,
                "invalid_run_count": len(invalid_candidate_runs),
                "invalid_runs": invalid_candidate_runs,
            },
        },
        "reference": {
            "algorithm_name": reference_runs[0]["algorithm_name"],
            "scores": reference_scores,
            "aggregate": score_summary(reference_scores),
            "runs": reference_runs,
        },
        "theoretical_limit": task.theoretical_limit(),
    }
    result["score_gap"] = (
        result["reference"]["aggregate"]["mean"] - result["baseline"]["aggregate"]["mean"]
    )
    return result


def _frontier_eval_payload(result: dict) -> tuple[dict[str, float], dict[str, object]]:
    baseline_agg = result["baseline"]["aggregate"]
    reference_agg = result["reference"]["aggregate"]
    baseline_valid = bool(result["baseline"].get("validation", {}).get("all_valid", True))
    metrics = {
        "combined_score": float(baseline_agg["mean"]) if baseline_valid else 0.0,
        "candidate_score_mean": float(baseline_agg["mean"]),
        "candidate_score_std": float(baseline_agg["std"]),
        "reference_score_mean": float(reference_agg["mean"]),
        "score_gap": float(result["score_gap"]),
        "valid": 1.0 if baseline_valid else 0.0,
        "timeout": 0.0,
    }
    artifacts = {
        "task_name": result["task_name"],
        "candidate_path": result["candidate_path"],
        "budget": result["budget"],
        "seeds": result["seeds"],
        "candidate_algorithm_name": result["baseline"]["algorithm_name"],
        "reference_algorithm_name": result["reference"]["algorithm_name"],
        "candidate_scores": result["baseline"]["scores"],
        "reference_scores": result["reference"]["scores"],
        "score_gap": result["score_gap"],
        "candidate_validation": result["baseline"].get("validation", {}),
    }
    return metrics, artifacts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", nargs="?", default=str(DEFAULT_CANDIDATE_PATH))
    parser.add_argument("--budget", type=int, default=task.DEFAULT_BUDGET)
    parser.add_argument("--seeds", type=int, nargs="*", default=task.DEFAULT_SEEDS)
    parser.add_argument("--metrics-out", type=str, default=None)
    parser.add_argument("--artifacts-out", type=str, default=None)
    args = parser.parse_args()
    result = evaluate(
        candidate_path=Path(args.candidate).expanduser().resolve(),
        seeds=args.seeds,
        budget=args.budget,
    )
    metrics, artifacts = _frontier_eval_payload(result)
    write_json(args.metrics_out, metrics)
    write_json(args.artifacts_out, artifacts)
    print(dump_json(result))


if __name__ == "__main__":
    main()
