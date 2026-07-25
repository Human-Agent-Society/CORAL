#!/usr/bin/env python3
"""Calibrate v8 search difficulty and freeze treatment-sensitivity anchors."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

from experiments.multi_island_modular.simulate_hard_v8 import (
    BUDGETS,
    MIGRATION_EVERY,
    MODULE_COST,
    assert_treatment_sensitivity,
    table,
)
from experiments.multi_island_modular.tasks.hard_active_modular_landscape_v8.grader.src.hard_active_modular_landscape_v8_grader.grader import (  # type: ignore[import-not-found]
    BLOCKS,
    GROUP_WIDTH,
    GROUPS,
    WIDTH,
    active_score,
    rugged_group_score,
    targets_for,
)

ROOT = Path(__file__).resolve().parent
TASKDATA = ROOT / "tasks/hard_active_modular_landscape_v8/taskdata/hard_v8_seed_bundle.json"


def strict_local_maxima(seed: str, block: int, group: int) -> int:
    scores = {
        value: rugged_group_score(
            seed,
            block,
            group,
            f"{value:0{GROUP_WIDTH}b}",
        )
        for value in range(2**GROUP_WIDTH)
    }
    return sum(
        score > max(scores[value ^ (1 << bit)] for bit in range(GROUP_WIDTH))
        for value, score in scores.items()
    )


def seed_row(seed: str, seed_index: int) -> dict[str, Any]:
    targets = targets_for(seed)
    local_maxima = [
        strict_local_maxima(seed, block, group)
        for block in range(BLOCKS)
        for group in range(GROUPS)
    ]
    smooth_zero = statistics.fmean(
        active_score("0" * WIDTH, mode="smooth", seed=seed, block=block)
        for block in range(BLOCKS)
    )
    rugged_zero = statistics.fmean(
        active_score("0" * WIDTH, mode="rugged", seed=seed, block=block)
        for block in range(BLOCKS)
    )
    return {
        "seed_index": seed_index,
        "target_sha256": hashlib.sha256("".join(targets).encode()).hexdigest(),
        "unique_target_modules": len(set(targets)),
        "smooth_zero_mean_active_score": smooth_zero,
        "rugged_zero_mean_active_score": rugged_zero,
        "rugged_group_local_maxima_mean": statistics.fmean(local_maxima),
        "rugged_group_local_maxima_min": min(local_maxima),
        "rugged_group_local_maxima_max": max(local_maxima),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "hard_v8_calibration.json")
    args = parser.parse_args()
    bundle = json.loads(TASKDATA.read_text())
    seeds = bundle["seeds"]
    simulation = table()
    assert_treatment_sensitivity(simulation)
    result = {
        "schema_version": 6,
        "method": "certified submitted-artifact Smooth/Rugged threshold",
        "feedback": "active module plus portable exact certificate",
        "blocks": BLOCKS,
        "block_width": WIDTH,
        "rugged_group_width": GROUP_WIDTH,
        "rugged_groups_per_module": GROUPS,
        "seed_count": len(seeds),
        "module_cost_upper_bound": MODULE_COST,
        "full_artifact_cost_upper_bound": {
            mode: BLOCKS * cost for mode, cost in MODULE_COST.items()
        },
        "budgets": {mode: list(values) for mode, values in BUDGETS.items()},
        "migration_every": MIGRATION_EVERY,
        "per_seed": [seed_row(seed, index) for index, seed in enumerate(seeds)],
        "idealized_treatment_sensitivity": simulation,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
