"""Reference implementation for the MIT case 1 task."""

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

from mit_case1_mixed import task
from shared.summit_compat import apply_summit_compat
from shared.utils import dump_json, records_from_experiment_data, seed_everything


def solve(seed: int = 0, budget: int = task.DEFAULT_BUDGET) -> dict:
    apply_summit_compat()
    from summit.run import Runner
    from summit.strategies import SOBO

    seed_everything(seed)
    experiment = task.create_benchmark()
    strategy = SOBO(experiment.domain, use_descriptors=False)
    runner = Runner(strategy=strategy, experiment=experiment, max_iterations=budget, batch_size=1)
    runner.run(progress_bar=False)
    history = records_from_experiment_data(experiment, task.INPUT_NAMES, task.OBJECTIVE_NAMES)
    return {
        "task_name": task.TASK_NAME,
        "algorithm_name": "summit_sobo",
        "seed": seed,
        "budget": budget,
        "history": history,
        "summary": task.summarize(history),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--budget", type=int, default=task.DEFAULT_BUDGET)
    args = parser.parse_args()
    print(dump_json(solve(seed=args.seed, budget=args.budget)))


if __name__ == "__main__":
    main()
