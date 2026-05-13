"""Evaluate baseline and reference solutions for the SnAr task."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


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

from shared.cli import load_module, write_json
from shared.utils import dump_json, score_summary
from snar_multiobjective import task
from snar_multiobjective.verification.reference import solve as solve_reference

DEFAULT_CANDIDATE_PATH = Path(__file__).resolve().parents[1] / "baseline" / "solution.py"


def evaluate(candidate_path: Path, seeds: list[int], budget: int) -> dict:
    candidate_module = load_module(candidate_path, f"{task.TASK_NAME}_candidate")
    solve_candidate = getattr(candidate_module, "solve", None)
    if not callable(solve_candidate):
        raise AttributeError(f"{candidate_path} does not define a callable `solve`.")

    baseline_runs = []
    reference_runs = []

    for seed in seeds:
        baseline = solve_candidate(seed=seed, budget=budget)
        reference = solve_reference(seed=seed, budget=budget)
        baseline_runs.append(baseline)
        reference_runs.append(reference)

    baseline_scores = [run["summary"]["score"] for run in baseline_runs]
    reference_scores = [run["summary"]["score"] for run in reference_runs]
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
    metrics = {
        "combined_score": float(baseline_agg["mean"]),
        "candidate_score_mean": float(baseline_agg["mean"]),
        "candidate_score_std": float(baseline_agg["std"]),
        "reference_score_mean": float(reference_agg["mean"]),
        "score_gap": float(result["score_gap"]),
        "valid": 1.0,
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
