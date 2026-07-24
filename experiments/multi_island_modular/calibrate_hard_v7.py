#!/usr/bin/env python3
"""Calibrate the v7 Smooth/Rugged difficulty ladder before agent runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path

from experiments.multi_island_modular.tasks.hard_active_modular_landscape_v7.grader.src.hard_active_modular_landscape_v7_grader.grader import (  # type: ignore[import-not-found]
    BLOCKS,
    CODEBOOK,
    CODEBOOK_SIZE,
    WIDTH,
    active_score,
    rugged_target,
    target_bits,
)

ROOT = Path(__file__).resolve().parent
TASKDATA = ROOT / "tasks/hard_active_modular_landscape_v7/taskdata/hard_v7_seed_bundle.json"


def smooth_cost() -> int:
    return BLOCKS * (WIDTH + 2)


def rugged_cost(seed: str) -> int:
    indices = [CODEBOOK.index(rugged_target(seed, block, WIDTH)) + 1 for block in range(BLOCKS)]
    targets = [rugged_target(seed, block, WIDTH) for block in range(BLOCKS)]
    if len(set(targets)) != BLOCKS:
        raise AssertionError("v7 rugged targets must be unique within a seed")
    return sum(indices)


def row(seed: str, mode: str, seed_index: int) -> dict[str, object]:
    targets = [
        target_bits(seed, block, WIDTH) if mode == "smooth" else rugged_target(seed, block, WIDTH)
        for block in range(BLOCKS)
    ]
    zero_score = statistics.fmean(
        active_score("0" * WIDTH, mode=mode, target=target) for target in targets
    )
    return {
        "seed_index": seed_index,
        "zero_mean_active_score": zero_score,
        "optimum_mean_active_score": 1.0,
        "target_sha256": hashlib.sha256("".join(targets).encode()).hexdigest(),
        "smooth_provenance_cost": smooth_cost() if mode == "smooth" else None,
        "rugged_ordered_codebook_cost": rugged_cost(seed) if mode == "rugged" else None,
        "unique_target_count": len(set(targets)),
    }


def oracle_table(seeds: list[str]) -> dict[str, list[dict[str, object]]]:
    smooth_budgets = [1024, 2048, 3072, 4096, 6144, 8192]
    smooth = [
        {
            "budget": budget,
            "serial_exact_modules": min(BLOCKS, budget // (WIDTH + 2)),
        }
        for budget in smooth_budgets
    ]
    rugged = []
    for budget in [16384, 32768, 65536, 98304, 131072, 196608]:
        counts = []
        for seed in seeds:
            indices = [CODEBOOK.index(rugged_target(seed, block, WIDTH)) + 1 for block in range(BLOCKS)]
            quotient, remainder = divmod(budget, BLOCKS)
            counts.append(
                sum(index <= quotient + int(block < remainder) for block, index in enumerate(indices))
            )
        rugged.append(
            {
                "budget": budget,
                "breadth_first_exact_modules": counts,
                "mean": statistics.fmean(counts),
                "min": min(counts),
                "max": max(counts),
            }
        )
    return {"smooth": smooth, "rugged": rugged}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "hard_v7_calibration.json")
    args = parser.parse_args()
    bundle = json.loads(TASKDATA.read_text())
    seeds = bundle["seeds"]
    tasks = []
    for mode, name in (("smooth", "smooth_hard_v7"), ("rugged", "rugged_hard_v7")):
        key = "smooth_provenance_cost" if mode == "smooth" else "rugged_ordered_codebook_cost"
        rows = [row(seed, mode, index) for index, seed in enumerate(seeds)]
        costs = [int(item[key]) for item in rows]
        tasks.append(
            {
                "task": name,
                "mode": mode,
                "blocks": BLOCKS,
                "block_width": WIDTH,
                "codebook_size": CODEBOOK_SIZE if mode == "rugged" else None,
                "public_codebook_sha256": hashlib.sha256("".join(CODEBOOK).encode()).hexdigest()
                if mode == "rugged"
                else None,
                "per_seed": rows,
                "cost_mean": statistics.fmean(costs),
                "cost_min": min(costs),
                "cost_max": max(costs),
            }
        )
    result = {
        "schema_version": 5,
        "method": "v7 oracle-free smooth coordinate and rugged ordered-codebook anchors",
        "feedback": "active_module_only",
        "budgets": [1024, 2048, 3072, 4096, 6144, 8192, 16384, 32768, 65536, 98304, 131072, 196608],
        "seed_count": len(seeds),
        "idealized_oracle": oracle_table(seeds),
        "tasks": tasks,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
