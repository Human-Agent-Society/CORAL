"""Task definition for the SnAr multi-objective benchmark."""

from __future__ import annotations

from typing import Any

import numpy as np

from shared.metrics import hypervolume_2d_min, pareto_mask
from shared.summit_compat import apply_summit_compat
from shared.utils import clamp, evaluate_candidate

TASK_NAME = "snar_multiobjective"
TASK_TITLE = "Continuous-flow SnAr reaction optimization"
DEFAULT_BUDGET = 24
DEFAULT_SEEDS = [0, 1, 2]
INPUT_NAMES = ["tau", "equiv_pldn", "conc_dfnb", "temperature"]
OBJECTIVE_NAMES = ["sty", "e_factor"]
OBJECTIVE_DIRECTIONS = {"sty": True, "e_factor": False}
BOUNDS = {
    "tau": (0.5, 2.0),
    "equiv_pldn": (1.0, 5.0),
    "conc_dfnb": (0.1, 0.5),
    "temperature": (30.0, 120.0),
}
NORMALIZATION = {"sty": (0.0, 13000.0), "e_factor": (0.0, 500.0)}


def create_benchmark():
    apply_summit_compat()
    from summit.benchmarks import SnarBenchmark

    return SnarBenchmark(noise_level=0)


def sample_candidate(rng: np.random.Generator) -> dict[str, float]:
    return {
        name: float(rng.uniform(low, high))
        for name, (low, high) in BOUNDS.items()
    }


def mutate_candidate(candidate: dict[str, Any], rng: np.random.Generator) -> dict[str, float]:
    proposal = dict(candidate)
    for name, (low, high) in BOUNDS.items():
        span = high - low
        step = float(rng.normal(0.0, 0.12 * span))
        if rng.random() < 0.25:
            proposal[name] = float(rng.uniform(low, high))
        else:
            proposal[name] = clamp(float(candidate[name]) + step, low, high)
    return proposal


def evaluate(experiment, candidate: dict[str, Any]) -> dict[str, Any]:
    return evaluate_candidate(experiment, candidate)


def scalarize(record: dict[str, Any], weight: float) -> float:
    sty_norm = clamp(record["sty"] / NORMALIZATION["sty"][1], 0.0, 1.0)
    eco_norm = clamp(
        1.0 - record["e_factor"] / NORMALIZATION["e_factor"][1], 0.0, 1.0
    )
    return float(weight * sty_norm + (1.0 - weight) * eco_norm)


def summarize(history: list[dict[str, Any]]) -> dict[str, Any]:
    if not history:
        return {
            "score": 0.0,
            "hypervolume": 0.0,
            "pareto_size": 0,
            "best_sty": 0.0,
            "best_e_factor": float("inf"),
        }

    points = []
    for row in history:
        sty_norm = clamp(row["sty"] / NORMALIZATION["sty"][1], 0.0, 1.0)
        eco_norm = clamp(
            1.0 - row["e_factor"] / NORMALIZATION["e_factor"][1], 0.0, 1.0
        )
        points.append([1.0 - sty_norm, 1.0 - eco_norm])
    point_array = np.asarray(points, dtype=float)
    hv = hypervolume_2d_min(point_array, ref_point=np.array([1.0, 1.0]))
    mask = pareto_mask(
        np.asarray([[row["sty"], row["e_factor"]] for row in history], dtype=float),
        maximize=[True, False],
    )
    return {
        "score": float(hv * 100.0),
        "hypervolume": float(hv),
        "pareto_size": int(mask.sum()),
        "best_sty": float(max(row["sty"] for row in history)),
        "best_e_factor": float(min(row["e_factor"] for row in history)),
    }


def theoretical_limit() -> dict[str, Any] | None:
    return None
