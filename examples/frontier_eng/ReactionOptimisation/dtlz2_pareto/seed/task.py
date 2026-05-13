"""Task definition for the DTLZ2 multi-objective benchmark."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from shared.metrics import hypervolume_2d_min, pareto_mask
from shared.summit_compat import apply_summit_compat
from shared.utils import clamp, evaluate_candidate

TASK_NAME = "dtlz2_pareto"
TASK_TITLE = "DTLZ2 Pareto front approximation"
DEFAULT_BUDGET = 30
DEFAULT_SEEDS = [0, 1, 2]
INPUT_NAMES = [f"x_{i}" for i in range(6)]
OBJECTIVE_NAMES = ["y_0", "y_1"]
OBJECTIVE_DIRECTIONS = {"y_0": False, "y_1": False}
REFERENCE_POINT = np.array([1.1, 1.1], dtype=float)


def create_benchmark():
    apply_summit_compat()
    from summit.benchmarks import DTLZ2

    return DTLZ2(num_inputs=6, num_objectives=2)


def sample_candidate(rng: np.random.Generator) -> dict[str, float]:
    return {name: float(rng.uniform(0.0, 1.0)) for name in INPUT_NAMES}


def mutate_candidate(candidate: dict[str, Any], rng: np.random.Generator) -> dict[str, float]:
    proposal: dict[str, float] = {}
    for name in INPUT_NAMES:
        if rng.random() < 0.15:
            proposal[name] = float(rng.uniform(0.0, 1.0))
            continue
        proposal[name] = clamp(float(candidate[name]) + float(rng.normal(0.0, 0.08)), 0.0, 1.0)
    return proposal


def evaluate(experiment, candidate: dict[str, Any]) -> dict[str, Any]:
    return evaluate_candidate(experiment, candidate)


def scalarize(record: dict[str, Any], weight: float) -> float:
    return -float(weight * record["y_0"] + (1.0 - weight) * record["y_1"])


def theoretical_hypervolume() -> float:
    return float(REFERENCE_POINT[0] * REFERENCE_POINT[1] - math.pi / 4.0)


def summarize(history: list[dict[str, Any]]) -> dict[str, Any]:
    if not history:
        return {
            "score": 0.0,
            "hypervolume": 0.0,
            "pareto_size": 0,
            "best_y_0": float("inf"),
            "best_y_1": float("inf"),
            "theoretical_hypervolume": theoretical_hypervolume(),
        }

    points = np.asarray([[row["y_0"], row["y_1"]] for row in history], dtype=float)
    hv = hypervolume_2d_min(points, ref_point=REFERENCE_POINT)
    ceiling = theoretical_hypervolume()
    mask = pareto_mask(points, maximize=[False, False])
    return {
        "score": float(clamp(hv / ceiling if ceiling > 0 else 0.0, 0.0, 1.0) * 100.0),
        "hypervolume": float(hv),
        "pareto_size": int(mask.sum()),
        "best_y_0": float(points[:, 0].min()),
        "best_y_1": float(points[:, 1].min()),
        "theoretical_hypervolume": float(ceiling),
    }


def theoretical_limit() -> dict[str, Any] | None:
    ceiling = theoretical_hypervolume()
    return {"score": 100.0, "hypervolume": ceiling, "description": "Exact Pareto front"}
