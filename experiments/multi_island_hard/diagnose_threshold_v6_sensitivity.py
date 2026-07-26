#!/usr/bin/env python3
"""Report preregistered v6 design sensitivity without reading outcomes."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "threshold_v6_sensitivity_diagnostics_v2.json"
FAMILYWISE_ALPHA = 0.05
TARGET_POWER = 0.80
PAIRED_EFFECT_SD_GRID = (0.25, 0.5, 0.75, 1.0)
DESIGNS = {
    "original_v6": {
        "blocks": 24,
        "rugged_cells": 25,
        "floors": {"multi_minus_global": 0.25, "multi_minus_partition": 0.10},
    },
    "extreme_extension": {
        "blocks": 64,
        "rugged_cells": 12,
        "floors": {"multi_minus_global": 0.25, "multi_minus_partition": 0.10},
    },
}


def critical_z(*, cells: int) -> float:
    alpha_per_contrast = FAMILYWISE_ALPHA / (cells * 2)
    return NormalDist().inv_cdf(1 - alpha_per_contrast)


def approximate_power(
    *,
    effect: float,
    paired_effect_sd: float,
    blocks: int,
    cells: int,
) -> float:
    if effect <= 0 or paired_effect_sd <= 0 or blocks < 2 or cells < 1:
        raise ValueError("invalid sensitivity inputs")
    signal_z = effect * math.sqrt(blocks) / paired_effect_sd
    return NormalDist().cdf(signal_z - critical_z(cells=cells))


def minimum_detectable_effect(
    *,
    paired_effect_sd: float,
    blocks: int,
    cells: int,
    target_power: float = TARGET_POWER,
) -> float:
    if paired_effect_sd <= 0 or blocks < 2 or cells < 1 or not 0 < target_power < 1:
        raise ValueError("invalid sensitivity inputs")
    return (
        (critical_z(cells=cells) + NormalDist().inv_cdf(target_power))
        * paired_effect_sd
        / math.sqrt(blocks)
    )


def required_blocks(
    *,
    effect: float,
    paired_effect_sd: float,
    cells: int,
    target_power: float = TARGET_POWER,
) -> int:
    if effect <= 0 or paired_effect_sd <= 0 or cells < 1 or not 0 < target_power < 1:
        raise ValueError("invalid sensitivity inputs")
    z_sum = critical_z(cells=cells) + NormalDist().inv_cdf(target_power)
    return max(2, math.ceil((z_sum * paired_effect_sd / effect) ** 2))


def run_diagnostics() -> dict[str, Any]:
    designs: list[dict[str, Any]] = []
    for name, design in DESIGNS.items():
        cells = int(design["rugged_cells"])
        blocks = int(design["blocks"])
        rows = []
        for contrast, floor in design["floors"].items():
            for paired_effect_sd in PAIRED_EFFECT_SD_GRID:
                rows.append(
                    {
                        "contrast": contrast,
                        "practical_floor_random_z": floor,
                        "assumed_paired_effect_sd_random_z": paired_effect_sd,
                        "approximate_power_at_floor": approximate_power(
                            effect=floor,
                            paired_effect_sd=paired_effect_sd,
                            blocks=blocks,
                            cells=cells,
                        ),
                        "minimum_detectable_effect_for_80pct_power_random_z": (
                            minimum_detectable_effect(
                                paired_effect_sd=paired_effect_sd,
                                blocks=blocks,
                                cells=cells,
                            )
                        ),
                        "blocks_required_for_80pct_power_at_floor": required_blocks(
                            effect=floor,
                            paired_effect_sd=paired_effect_sd,
                            cells=cells,
                        ),
                    }
                )
        designs.append(
            {
                "design": name,
                "rugged_cells": cells,
                "contrasts_per_cell": 2,
                "blocks": blocks,
                "familywise_alpha": FAMILYWISE_ALPHA,
                "one_sided_alpha_per_contrast": FAMILYWISE_ALPHA / (cells * 2),
                "normal_critical_z": critical_z(cells=cells),
                "rows": rows,
            }
        )
    return {
        "schema_version": 1,
        "purpose": "outcome-free design sensitivity for v6 Rugged confirmatory gates",
        "method": (
            "One-sided normal approximation using the registered Bonferroni alpha, "
            "24 independent paired blocks, and a grid of paired-effect SDs."
        ),
        "target_power": TARGET_POWER,
        "paired_effect_sd_grid_random_z": list(PAIRED_EFFECT_SD_GRID),
        "designs": designs,
        "interpretation": (
            "This diagnostic reads no topology outcome and cannot establish an effect. "
            "After results exist, a failed gate must not be described as evidence of no "
            "practically relevant effect when observed block dispersion lies in a region "
            "where the registered design has low power at that floor."
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
