#!/usr/bin/env python3
"""Outcome-free sensitivity audit for natural-agent and real-task validation."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "external_validation_sensitivity.json"
TARGET_POWER = 0.80

DESIGNS: dict[str, dict[str, Any]] = {
    "natural_discovery": {
        "blocks": 8,
        "one_sided_alpha": 0.025,
        "effect_scale": "rugged_random_z",
        "floors": {
            "multi_minus_global": 0.25,
            "multi_minus_partition": 0.10,
        },
        "target_surplus": 0.10,
        "paired_sd_grid": (0.25, 0.50, 0.75, 1.00),
    },
    "natural_fresh_confirmation": {
        "blocks": 40,
        "one_sided_alpha": 0.05,
        "effect_scale": "rugged_random_z",
        "floors": {
            "multi_minus_global": 0.25,
            "multi_minus_partition": 0.10,
        },
        "target_surplus": 0.10,
        "paired_sd_grid": (0.25, 0.50, 0.75, 1.00),
    },
    "circle_discovery": {
        "blocks": 8,
        "one_sided_alpha": 0.05 / 3,
        "effect_scale": "normalized_circle_score",
        "floors": {
            "multi_minus_global": 0.01,
            "multi_minus_partition": 0.01,
        },
        "target_surplus": 0.01,
        "paired_sd_grid": (0.005, 0.010, 0.020, 0.040),
    },
    "circle_selected_budget_fresh_confirmation": {
        "blocks": 32,
        "one_sided_alpha": 0.05,
        "effect_scale": "normalized_circle_score",
        "floors": {
            "multi_minus_global": 0.01,
            "multi_minus_partition": 0.01,
        },
        "target_surplus": 0.01,
        "paired_sd_grid": (0.005, 0.010, 0.020, 0.040),
    },
}


def critical_z(one_sided_alpha: float) -> float:
    if not 0 < one_sided_alpha < 0.5:
        raise ValueError("one-sided alpha must lie in (0, 0.5)")
    return NormalDist().inv_cdf(1 - one_sided_alpha)


def approximate_gate_power(
    *,
    true_effect: float,
    practical_floor: float,
    paired_effect_sd: float,
    blocks: int,
    one_sided_alpha: float,
) -> float:
    if (
        true_effect <= 0
        or practical_floor < 0
        or paired_effect_sd <= 0
        or blocks < 2
    ):
        raise ValueError("invalid validation sensitivity inputs")
    standard_error = paired_effect_sd / math.sqrt(blocks)
    threshold = max(practical_floor, critical_z(one_sided_alpha) * standard_error)
    return NormalDist().cdf((true_effect - threshold) / standard_error)


def required_blocks(
    *,
    true_effect: float,
    practical_floor: float,
    paired_effect_sd: float,
    one_sided_alpha: float,
    target_power: float = TARGET_POWER,
) -> int:
    if not 0 < target_power < 1:
        raise ValueError("target power must lie in (0, 1)")
    for blocks in range(2, 100_001):
        if (
            approximate_gate_power(
                true_effect=true_effect,
                practical_floor=practical_floor,
                paired_effect_sd=paired_effect_sd,
                blocks=blocks,
                one_sided_alpha=one_sided_alpha,
            )
            >= target_power
        ):
            return blocks
    raise ValueError("required block count exceeds audited search range")


def design_rows(name: str, design: dict[str, Any]) -> dict[str, Any]:
    blocks = int(design["blocks"])
    alpha = float(design["one_sided_alpha"])
    surplus = float(design["target_surplus"])
    rows = []
    for contrast, floor_value in design["floors"].items():
        floor = float(floor_value)
        target = floor + surplus
        for paired_sd_value in design["paired_sd_grid"]:
            paired_sd = float(paired_sd_value)
            rows.append(
                {
                    "contrast": contrast,
                    "practical_floor": floor,
                    "target_true_effect": target,
                    "target_surplus_over_floor": surplus,
                    "assumed_paired_effect_sd": paired_sd,
                    "approximate_gate_power_at_target_effect": approximate_gate_power(
                        true_effect=target,
                        practical_floor=floor,
                        paired_effect_sd=paired_sd,
                        blocks=blocks,
                        one_sided_alpha=alpha,
                    ),
                    "blocks_required_for_80pct_gate_power": required_blocks(
                        true_effect=target,
                        practical_floor=floor,
                        paired_effect_sd=paired_sd,
                        one_sided_alpha=alpha,
                    ),
                }
            )
    return {
        "design": name,
        "blocks": blocks,
        "one_sided_alpha_each_required_component": alpha,
        "effect_scale": design["effect_scale"],
        "target_surplus_over_floor": surplus,
        "rows": rows,
    }


def run_diagnostics() -> dict[str, Any]:
    designs = [design_rows(name, design) for name, design in DESIGNS.items()]
    natural_confirmation = next(
        row for row in designs if row["design"] == "natural_fresh_confirmation"
    )
    circle_confirmation = next(
        row
        for row in designs
        if row["design"] == "circle_selected_budget_fresh_confirmation"
    )
    natural_target_rows = [
        row
        for row in natural_confirmation["rows"]
        if row["assumed_paired_effect_sd"] <= 0.50
    ]
    circle_target_rows = [
        row
        for row in circle_confirmation["rows"]
        if row["assumed_paired_effect_sd"] <= 0.040
    ]
    return {
        "schema_version": 1,
        "purpose": "outcome-free sensitivity for external-validation discovery and confirmation",
        "method": (
            "Normal approximation to the actual per-contrast gate: the estimate must "
            "meet its practical floor and its one-sided lower bound must exceed zero. "
            "Fresh confirmation requires both multi-global and multi-partition components, "
            "so each uses alpha 0.05 as an intersection-union test."
        ),
        "target_power": TARGET_POWER,
        "designs": designs,
        "confirmation_design_gates": {
            "natural": {
                "paired_effect_sd_at_or_below": 0.50,
                "minimum_component_power": min(
                    row["approximate_gate_power_at_target_effect"]
                    for row in natural_target_rows
                ),
                "required_minimum_power": TARGET_POWER,
            },
            "circle": {
                "paired_effect_sd_at_or_below": 0.040,
                "minimum_component_power": min(
                    row["approximate_gate_power_at_target_effect"]
                    for row in circle_target_rows
                ),
                "required_minimum_power": TARGET_POWER,
            },
        },
        "interpretation": (
            "No natural-agent or Circle Packing outcome directory existed when this "
            "audit was frozen. Eight-block discovery failures cannot be described as "
            "evidence of no practically relevant effect outside their powered region."
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
