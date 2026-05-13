"""Task definition for the MIT case 1 mixed-variable benchmark."""

from __future__ import annotations

from typing import Any

import numpy as np

from shared.summit_compat import apply_summit_compat
from shared.utils import clamp, evaluate_candidate

TASK_NAME = "mit_case1_mixed"
TASK_TITLE = "MIT kinetic case 1 yield maximization"
DEFAULT_BUDGET = 20
DEFAULT_SEEDS = [0, 1, 2]
INPUT_NAMES = ["conc_cat", "t", "cat_index", "temperature"]
OBJECTIVE_NAMES = ["y"]
OBJECTIVE_DIRECTIONS = {"y": True}
BOUNDS = {
    "conc_cat": (0.000835, 0.004175),
    "t": (60.0, 600.0),
    "temperature": (30.0, 110.0),
}
CATEGORIES = {"cat_index": list(range(8))}


def create_benchmark():
    apply_summit_compat()
    from summit.benchmarks import MIT_case1

    return MIT_case1(noise_level=0)


def sample_candidate(rng: np.random.Generator) -> dict[str, Any]:
    candidate = {
        name: float(rng.uniform(low, high))
        for name, (low, high) in BOUNDS.items()
    }
    candidate["cat_index"] = int(rng.choice(CATEGORIES["cat_index"]))
    return candidate


def initial_candidates(rng: np.random.Generator) -> list[dict[str, Any]]:
    candidates = []
    for cat_index in CATEGORIES["cat_index"]:
        candidate = {
            "conc_cat": float(rng.uniform(*BOUNDS["conc_cat"])),
            "t": float(rng.uniform(*BOUNDS["t"])),
            "temperature": float(rng.uniform(*BOUNDS["temperature"])),
            "cat_index": int(cat_index),
        }
        candidates.append(candidate)
    return candidates


def mutate_candidate(candidate: dict[str, Any], rng: np.random.Generator) -> dict[str, Any]:
    proposal = dict(candidate)
    if rng.random() < 0.15:
        proposal["cat_index"] = int(rng.choice(CATEGORIES["cat_index"]))
    for name, (low, high) in BOUNDS.items():
        span = high - low
        step = float(rng.normal(0.0, 0.1 * span))
        if rng.random() < 0.2:
            proposal[name] = float(rng.uniform(low, high))
        else:
            proposal[name] = clamp(float(candidate[name]) + step, low, high)
    return proposal


def evaluate(experiment, candidate: dict[str, Any]) -> dict[str, Any]:
    return evaluate_candidate(experiment, candidate)


def is_better(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return float(left["y"]) > float(right["y"])


def summarize(history: list[dict[str, Any]]) -> dict[str, Any]:
    if not history:
        return {"score": 0.0, "best_y": 0.0}
    best_y = max(float(row["y"]) for row in history)
    return {
        "score": float(clamp(best_y, 0.0, 1.0) * 100.0),
        "best_y": float(best_y),
    }


def theoretical_limit() -> dict[str, Any] | None:
    return None
