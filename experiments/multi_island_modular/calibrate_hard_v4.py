#!/usr/bin/env python3
"""Calibrate the v4 smooth and rugged difficulty anchors."""

from __future__ import annotations

import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASKDATA = ROOT / "tasks/hard_active_modular_landscape_v4/taskdata/hard_v4_seed_bundle.json"
GRADER_SRC = ROOT / "tasks/hard_active_modular_landscape_v4/grader/src"
sys.path.insert(0, str(GRADER_SRC))
from hard_active_modular_landscape_grader.grader import (  # noqa: E402
    BLOCKS,
    CODEBOOK,
    CODEBOOK_SIZE,
    WIDTH,
    active_score,
    rugged_target,
    target_bits,
)


def load_seeds() -> list[str]:
    bundle = json.loads(TASKDATA.read_text())
    if (
        bundle.get("schema_version") != 2
        or bundle.get("blocks") != BLOCKS
        or bundle.get("block_width") != WIDTH
        or bundle.get("codebook_size") != CODEBOOK_SIZE
    ):
        raise ValueError("invalid v4 seed bundle")
    return [str(seed) for seed in bundle["seeds"]]


def smooth_cost() -> int:
    return BLOCKS * (WIDTH + 1)


def rugged_cost(seed: str) -> int:
    indices = [CODEBOOK.index(rugged_target(seed, block, WIDTH)) + 1 for block in range(BLOCKS)]
    if len(set(indices)) != BLOCKS:
        raise AssertionError("v4 rugged targets must be unique within a seed")
    return sum(indices)


def row(seed: str, mode: str, index: int) -> dict[str, object]:
    targets = [target_bits(seed, block, WIDTH) if mode == "smooth" else rugged_target(seed, block, WIDTH) for block in range(BLOCKS)]
    zeros = [active_score("0" * WIDTH, mode=mode, target=target) for target in targets]
    return {
        "seed_index": index,
        "zero_mean_active_score": statistics.fmean(zeros),
        "optimum_mean_active_score": 1.0,
        "target_sha256": hashlib.sha256("".join(targets).encode()).hexdigest(),
        "coordinate_probe_cost": smooth_cost() if mode == "smooth" else None,
        "ordered_codebook_cost": rugged_cost(seed) if mode == "rugged" else None,
        "unique_target_count": len(set(targets)),
    }


def main() -> int:
    seeds = load_seeds()
    tasks = []
    for mode in ("smooth", "rugged"):
        rows = [row(seed, mode, index) for index, seed in enumerate(seeds)]
        costs = [int(item["coordinate_probe_cost"] if mode == "smooth" else item["ordered_codebook_cost"]) for item in rows]
        tasks.append(
            {
                "task": f"{mode}_hard_v4",
                "mode": mode,
                "blocks": BLOCKS,
                "block_width": WIDTH,
                "codebook_size": CODEBOOK_SIZE if mode == "rugged" else None,
                "public_codebook_sha256": hashlib.sha256("".join(CODEBOOK).encode()).hexdigest() if mode == "rugged" else None,
                "per_seed": rows,
                "cost_mean": statistics.fmean(costs),
                "cost_min": min(costs),
                "cost_max": max(costs),
            }
        )
    report = {
        "schema_version": 2,
        "method": "coordinate-probe and ordered-public-codebook anchors with unique rugged targets",
        "budgets": [384, 768, 1536, 3072, 6144, 8192],
        "seed_count": len(seeds),
        "tasks": tasks,
    }
    output = ROOT / "hard_v4_calibration.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
