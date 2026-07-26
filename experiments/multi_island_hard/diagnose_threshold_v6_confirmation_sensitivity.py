#!/usr/bin/env python3
"""Outcome-free power audit for the selected-cell confirmation design."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any

from experiments.multi_island_hard import select_threshold_v6_extreme_confirmation as selector

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "threshold_v6_extreme_confirmation_sensitivity.json"
ONE_SIDED_ALPHA = 0.05
TARGET_POWER = 0.80
PAIRED_EFFECT_SD_GRID = (0.25, 0.5, 0.75, 1.0)
TARGET_SURPLUS_OVER_FLOOR_Z = 0.05


def critical_z() -> float:
    return NormalDist().inv_cdf(1 - ONE_SIDED_ALPHA)


def approximate_gate_power(
    *,
    true_effect: float,
    practical_floor: float,
    paired_effect_sd: float,
    blocks: int,
) -> float:
    if (
        true_effect <= 0
        or practical_floor < 0
        or paired_effect_sd <= 0
        or blocks < 2
    ):
        raise ValueError("invalid confirmation sensitivity inputs")
    standard_error = paired_effect_sd / math.sqrt(blocks)
    # Passing requires both estimate >= floor and lower one-sided bound > 0.
    sample_mean_threshold = max(practical_floor, critical_z() * standard_error)
    return NormalDist().cdf((true_effect - sample_mean_threshold) / standard_error)


def minimum_true_effect(
    *,
    practical_floor: float,
    paired_effect_sd: float,
    blocks: int,
    target_power: float = TARGET_POWER,
) -> float:
    if not 0 < target_power < 1:
        raise ValueError("target power must lie between zero and one")
    standard_error = paired_effect_sd / math.sqrt(blocks)
    sample_mean_threshold = max(practical_floor, critical_z() * standard_error)
    return sample_mean_threshold + NormalDist().inv_cdf(target_power) * standard_error


def run_diagnostics() -> dict[str, Any]:
    floors = {
        "multi_minus_global": selector.MULTI_GLOBAL_FLOOR_Z,
        "multi_minus_partition": selector.MULTI_PARTITION_FLOOR_Z,
    }
    rows = []
    for contrast, floor in floors.items():
        target_effect = floor + TARGET_SURPLUS_OVER_FLOOR_Z
        for paired_effect_sd in PAIRED_EFFECT_SD_GRID:
            rows.append(
                {
                    "contrast": contrast,
                    "practical_floor_random_z": floor,
                    "target_true_effect_random_z": target_effect,
                    "target_surplus_over_floor_random_z": TARGET_SURPLUS_OVER_FLOOR_Z,
                    "assumed_paired_effect_sd_random_z": paired_effect_sd,
                    "approximate_gate_power_at_target_effect": approximate_gate_power(
                        true_effect=target_effect,
                        practical_floor=floor,
                        paired_effect_sd=paired_effect_sd,
                        blocks=selector.CONFIRMATION_BLOCKS,
                    ),
                    "minimum_true_effect_for_80pct_gate_power_random_z": minimum_true_effect(
                        practical_floor=floor,
                        paired_effect_sd=paired_effect_sd,
                        blocks=selector.CONFIRMATION_BLOCKS,
                    ),
                }
            )
    return {
        "schema_version": 1,
        "purpose": "outcome-free sensitivity audit for fresh selected-cell confirmation",
        "method": (
            "One-sided normal approximation for the joint per-contrast gate: the point "
            "estimate must meet its practical floor and its one-sided 95% lower bound "
            "must exceed zero. Cell selection uses independent discovery blocks, and the "
            "positive claim is an intersection-union test requiring both contrasts, so "
            "alpha is not divided across discovery cells or the two component nulls."
        ),
        "blocks": selector.CONFIRMATION_BLOCKS,
        "one_sided_alpha_each_component": ONE_SIDED_ALPHA,
        "target_power": TARGET_POWER,
        "paired_effect_sd_grid_random_z": list(PAIRED_EFFECT_SD_GRID),
        "target_surplus_over_floor_random_z": TARGET_SURPLUS_OVER_FLOOR_Z,
        "rows": rows,
        "design_gate": {
            "paired_effect_sd_random_z_at_or_below": 0.75,
            "minimum_power_at_target_surplus": min(
                row["approximate_gate_power_at_target_effect"]
                for row in rows
                if row["assumed_paired_effect_sd_random_z"] <= 0.75
            ),
            "required_minimum_power": TARGET_POWER,
        },
        "interpretation": (
            "This calculation reads no topology outcome. Correlation between the two "
            "contrasts is unknown, so it reports component powers rather than inventing "
            "a joint-power number. A failed confirmation remains inconclusive if observed "
            "paired dispersion lies beyond the audited design range."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = run_diagnostics()
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
