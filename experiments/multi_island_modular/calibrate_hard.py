#!/usr/bin/env python3
"""Operator-side calibration for the hard modular task pair."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASKDATA = ROOT / "tasks/hard_active_modular_landscape/taskdata/hard_seed_bundle.json"
GRADER_SRC = ROOT / "tasks/hard_active_modular_landscape/grader/src"

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budgets", type=int, nargs="+", default=[256, 512, 1024, 2048, 4096])
    parser.add_argument("--output", type=Path, default=ROOT / "hard_calibration.json")
    return parser.parse_args()


def seed_bundle() -> list[str]:
    data = json.loads(TASKDATA.read_text())
    if data.get("schema_version") != 1 or data.get("blocks") != BLOCKS or data.get("block_width") != WIDTH:
        raise ValueError("invalid hard seed bundle")
    return [str(seed) for seed in data["seeds"]]


def smooth_probe_cost(seed: str) -> int:
    """Cost of the deliberately simple baseline: zero + one bit per module.

    This is not an LLM upper bound. It is a conservative calibration anchor
    showing when a straightforward coordinate probe can identify every target
    bit and then submit the exact module.
    """
    return BLOCKS * (WIDTH + 1)


def rugged_ordered_cost(seed: str) -> int:
    indices = []
    for block in range(BLOCKS):
        target = rugged_target(seed, block, WIDTH)
        indices.append(CODEBOOK.index(target) + 1)
    return sum(indices)


def baseline_summary(seed: str, mode: str) -> dict[str, object]:
    targets = [target_bits(seed, b, WIDTH) if mode == "smooth" else rugged_target(seed, b, WIDTH) for b in range(BLOCKS)]
    zero_scores = [active_score("0" * WIDTH, mode=mode, target=target) for target in targets]
    optimum_scores = [active_score(target, mode=mode, target=target) for target in targets]
    return {
        "zero_mean_active_score": statistics.fmean(zero_scores),
        "optimum_mean_active_score": statistics.fmean(optimum_scores),
        "target_sha256": hashlib.sha256("".join(targets).encode()).hexdigest(),
        "smooth_coordinate_cost": smooth_probe_cost(seed) if mode == "smooth" else None,
        "rugged_ordered_codebook_cost": rugged_ordered_cost(seed) if mode == "rugged" else None,
    }


def main() -> int:
    args = parse_args()
    seeds = seed_bundle()
    tasks: list[dict[str, object]] = []
    for mode in ("smooth", "rugged"):
        rows = []
        for index, seed in enumerate(seeds):
            row = {"seed_index": index, **baseline_summary(seed, mode)}
            rows.append(row)
        costs = [
            int(row["smooth_coordinate_cost"] if mode == "smooth" else row["rugged_ordered_codebook_cost"])
            for row in rows
        ]
        tasks.append(
            {
                "task": f"{mode}_hard256",
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
        "schema_version": 1,
        "method": "conservative coordinate-probe and ordered-public-codebook anchors",
        "budgets": args.budgets,
        "seed_count": len(seeds),
        "tasks": tasks,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
