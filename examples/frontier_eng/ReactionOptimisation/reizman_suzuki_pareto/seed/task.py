"""Task definition for the Reizman Suzuki emulator benchmark."""

from __future__ import annotations

from typing import Any

import numpy as np

from shared.metrics import hypervolume_2d_min, pareto_mask
from shared.summit_compat import apply_summit_compat
from shared.utils import clamp, evaluate_candidate

TASK_NAME = "reizman_suzuki_pareto"
TASK_TITLE = "Reizman Suzuki emulator Pareto optimization"
DEFAULT_BUDGET = 24
DEFAULT_SEEDS = [0, 1, 2]
INPUT_NAMES = ["catalyst", "t_res", "temperature", "catalyst_loading"]
OBJECTIVE_NAMES = ["ton", "yld"]
OBJECTIVE_DIRECTIONS = {"ton": False, "yld": True}
BOUNDS = {
    "t_res": (60.0, 600.0),
    "temperature": (30.0, 110.0),
    "catalyst_loading": (0.5, 2.5),
}
CATEGORIES = {
    "catalyst": [
        "P1-L1",
        "P2-L1",
        "P1-L2",
        "P1-L3",
        "P1-L4",
        "P1-L5",
        "P1-L6",
        "P1-L7",
    ]
}
NORMALIZATION = {"yld": (0.0, 100.0), "ton": (0.0, 200.0)}


def create_benchmark():
    apply_summit_compat()
    from summit.benchmarks import get_pretrained_reizman_suzuki_emulator

    return get_pretrained_reizman_suzuki_emulator(case=1)


def sample_candidate(rng: np.random.Generator) -> dict[str, Any]:
    candidate = {
        name: float(rng.uniform(low, high))
        for name, (low, high) in BOUNDS.items()
    }
    candidate["catalyst"] = str(rng.choice(CATEGORIES["catalyst"]))
    return candidate


def initial_candidates(rng: np.random.Generator) -> list[dict[str, Any]]:
    candidates = []
    for catalyst in CATEGORIES["catalyst"]:
        candidates.append(
            {
                "catalyst": catalyst,
                "t_res": float(rng.uniform(*BOUNDS["t_res"])),
                "temperature": float(rng.uniform(*BOUNDS["temperature"])),
                "catalyst_loading": float(rng.uniform(*BOUNDS["catalyst_loading"])),
            }
        )
    return candidates


def mutate_candidate(candidate: dict[str, Any], rng: np.random.Generator) -> dict[str, Any]:
    proposal = dict(candidate)
    if rng.random() < 0.2:
        proposal["catalyst"] = str(rng.choice(CATEGORIES["catalyst"]))
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


def scalarize(record: dict[str, Any], weight: float) -> float:
    yld_norm = clamp(record["yld"] / NORMALIZATION["yld"][1], 0.0, 1.0)
    ton_norm = clamp(1.0 - record["ton"] / NORMALIZATION["ton"][1], 0.0, 1.0)
    return float(weight * yld_norm + (1.0 - weight) * ton_norm)


def summarize(history: list[dict[str, Any]]) -> dict[str, Any]:
    if not history:
        return {
            "score": 0.0,
            "hypervolume": 0.0,
            "pareto_size": 0,
            "best_yld": 0.0,
            "best_ton": float("inf"),
        }

    points = []
    for row in history:
        yld_norm = clamp(row["yld"] / NORMALIZATION["yld"][1], 0.0, 1.0)
        ton_norm = clamp(1.0 - row["ton"] / NORMALIZATION["ton"][1], 0.0, 1.0)
        points.append([1.0 - yld_norm, 1.0 - ton_norm])
    point_array = np.asarray(points, dtype=float)
    hv = hypervolume_2d_min(point_array, ref_point=np.array([1.0, 1.0]))
    mask = pareto_mask(
        np.asarray([[row["ton"], row["yld"]] for row in history], dtype=float),
        maximize=[False, True],
    )
    return {
        "score": float(hv * 100.0),
        "hypervolume": float(hv),
        "pareto_size": int(mask.sum()),
        "best_yld": float(max(row["yld"] for row in history)),
        "best_ton": float(min(row["ton"] for row in history)),
    }


def theoretical_limit() -> dict[str, Any] | None:
    return None
