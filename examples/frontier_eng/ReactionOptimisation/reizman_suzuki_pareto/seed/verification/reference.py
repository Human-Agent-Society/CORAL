"""Reference implementation for the Reizman Suzuki emulator task."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd


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

from reizman_suzuki_pareto import task
from shared.summit_compat import apply_summit_compat
from shared.utils import dump_json, seed_everything, split_budget


def _make_prev_res(candidate: dict, value: float):
    apply_summit_compat()
    from summit.utils.dataset import DataSet

    return DataSet.from_df(
        pd.DataFrame(
            [
                {
                    "t_res": candidate["t_res"],
                    "temperature": candidate["temperature"],
                    "catalyst_loading": candidate["catalyst_loading"],
                    "merit": value,
                }
            ]
        )
    )


def _run_fixed_catalyst_sobo(
    *,
    seed: int,
    budget: int,
    weight: float,
    catalyst: str,
    initial_record: dict,
) -> list[dict]:
    apply_summit_compat()
    from summit.domain import ContinuousVariable, Domain
    from summit.strategies import SOBO

    if budget <= 0:
        return []

    domain = Domain()
    domain += ContinuousVariable("t_res", "Residence time", list(task.BOUNDS["t_res"]))
    domain += ContinuousVariable(
        "temperature", "Temperature", list(task.BOUNDS["temperature"])
    )
    domain += ContinuousVariable(
        "catalyst_loading",
        "Catalyst loading",
        list(task.BOUNDS["catalyst_loading"]),
    )
    domain += ContinuousVariable(
        "merit",
        "Scalarized merit",
        [0.0, 1.0],
        is_objective=True,
        maximize=True,
    )

    seed_everything(seed)
    strategy = SOBO(domain, use_descriptors=False)
    experiment = task.create_benchmark()
    history: list[dict] = []
    prev_res = _make_prev_res(initial_record, task.scalarize(initial_record, weight))

    for _ in range(budget):
        suggestion = strategy.suggest_experiments(num_experiments=1, prev_res=prev_res)
        row = suggestion.iloc[0]
        candidate = {
            "catalyst": catalyst,
            "t_res": float(
                row[("t_res", "DATA")] if ("t_res", "DATA") in suggestion.columns else row["t_res"]
            ),
            "temperature": float(
                row[("temperature", "DATA")]
                if ("temperature", "DATA") in suggestion.columns
                else row["temperature"]
            ),
            "catalyst_loading": float(
                row[("catalyst_loading", "DATA")]
                if ("catalyst_loading", "DATA") in suggestion.columns
                else row["catalyst_loading"]
            ),
        }
        record = task.evaluate(experiment, candidate)
        history.append(record)
        prev_res = _make_prev_res(record, task.scalarize(record, weight))
    return history


def _screen_catalysts() -> list[dict]:
    experiment = task.create_benchmark()
    history: list[dict] = []
    for catalyst in task.CATEGORIES["catalyst"]:
        candidate = {
            "catalyst": catalyst,
            "t_res": 360.0,
            "temperature": 100.0,
            "catalyst_loading": 2.0,
        }
        history.append(task.evaluate(experiment, candidate))
    return history


def solve(seed: int = 0, budget: int = task.DEFAULT_BUDGET) -> dict:
    seed_everything(seed)
    screening = _screen_catalysts()
    weights = [0.2, 0.5, 0.8]
    remaining_budget = max(0, budget - len(screening))
    sub_budgets = split_budget(remaining_budget, len(weights))

    history: list[dict] = list(screening)
    scored = []
    for weight in weights:
        ranked = sorted(
            screening,
            key=lambda row: task.scalarize(row, weight),
            reverse=True,
        )
        scored.append((weight, ranked[0]))

    for offset, ((weight, seed_record), sub_budget) in enumerate(zip(scored, sub_budgets)):
        history.extend(
            _run_fixed_catalyst_sobo(
                seed=seed + offset,
                budget=sub_budget,
                weight=weight,
                catalyst=str(seed_record["catalyst"]),
                initial_record=seed_record,
            )
        )

    return {
        "task_name": task.TASK_NAME,
        "algorithm_name": "screen_then_summit_sobo",
        "seed": seed,
        "budget": budget,
        "history": history[:budget],
        "summary": task.summarize(history[:budget]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--budget", type=int, default=task.DEFAULT_BUDGET)
    args = parser.parse_args()
    print(dump_json(solve(seed=args.seed, budget=args.budget)))


if __name__ == "__main__":
    main()
