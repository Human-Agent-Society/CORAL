from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_v6_sensitivity_registration_binds_blind_sources() -> None:
    directory = ROOT / "experiments/multi_island_hard"
    registration = json.loads(
        (directory / "threshold_v6_sensitivity_registration.json").read_text()
    )
    assert registration["original_phase_raw_absent_at_registration"] is True
    assert registration["extreme_phase_raw_absent_at_registration"] is True
    assert registration["sensitivity_output_absent_at_registration"] is True
    assert registration["superseded_by"] == "threshold_v6_sensitivity_registration_v2.json"


def test_v6_sensitivity_v2_registration_binds_64_block_design() -> None:
    directory = ROOT / "experiments/multi_island_hard"
    registration = json.loads(
        (directory / "threshold_v6_sensitivity_registration_v2.json").read_text()
    )
    assert registration["design_blocks"] == {
        "original_v6": 24,
        "extreme_extension": 64,
    }
    assert registration["original_phase_raw_absent_at_registration"] is True
    assert registration["extreme_phase_raw_absent_at_registration"] is True
    assert registration["sensitivity_v2_output_absent_at_registration"] is True
    assert registration["superseded_by"] == "threshold_v6_sensitivity_registration_v3.json"


def test_v6_sensitivity_v3_registration_binds_corrected_sources() -> None:
    directory = ROOT / "experiments/multi_island_hard"
    registration = json.loads(
        (directory / "threshold_v6_sensitivity_registration_v3.json").read_text()
    )
    assert registration["design_blocks"] == {
        "original_v6": 24,
        "extreme_extension": 64,
    }
    assert registration["supersession_changes_statistical_parameters"] is False
    assert registration["original_phase_raw_absent_at_registration"] is True
    assert registration["extreme_phase_raw_absent_at_registration"] is True
    assert registration["sensitivity_v3_output_absent_at_registration"] is True
    for filename, expected in registration["artifacts"].items():
        observed = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
        assert observed == expected


def test_v6_sensitivity_power_increases_with_effect_and_blocks() -> None:
    from experiments.multi_island_hard import diagnose_threshold_v6_sensitivity as diagnostic

    common = {"paired_effect_sd": 0.5, "cells": 25}
    baseline = diagnostic.approximate_power(effect=0.25, blocks=24, **common)
    assert diagnostic.approximate_power(effect=0.5, blocks=24, **common) > baseline
    assert diagnostic.approximate_power(effect=0.25, blocks=48, **common) > baseline


def test_v6_sensitivity_mde_and_required_blocks_are_consistent() -> None:
    from experiments.multi_island_hard import diagnose_threshold_v6_sensitivity as diagnostic

    for design in diagnostic.DESIGNS.values():
        cells = int(design["rugged_cells"])
        blocks = int(design["blocks"])
        for paired_effect_sd in diagnostic.PAIRED_EFFECT_SD_GRID:
            mde = diagnostic.minimum_detectable_effect(
                paired_effect_sd=paired_effect_sd,
                blocks=blocks,
                cells=cells,
            )
            power = diagnostic.approximate_power(
                effect=mde,
                paired_effect_sd=paired_effect_sd,
                blocks=blocks,
                cells=cells,
            )
            assert math.isclose(power, diagnostic.TARGET_POWER, abs_tol=1e-12)

            required = diagnostic.required_blocks(
                effect=0.25,
                paired_effect_sd=paired_effect_sd,
                cells=cells,
            )
            assert (
                diagnostic.approximate_power(
                    effect=0.25,
                    paired_effect_sd=paired_effect_sd,
                    blocks=required,
                    cells=cells,
                )
                >= diagnostic.TARGET_POWER
            )


def test_v6_sensitivity_artifact_has_both_frozen_designs() -> None:
    from experiments.multi_island_hard import diagnose_threshold_v6_sensitivity as diagnostic

    payload = diagnostic.run_diagnostics()
    assert "each design's registered independent paired-block count" in payload["method"]
    assert {row["design"] for row in payload["designs"]} == set(diagnostic.DESIGNS)
    assert all(len(row["rows"]) == 8 for row in payload["designs"])
    original = next(row for row in payload["designs"] if row["design"] == "original_v6")
    global_half_sd = next(
        row
        for row in original["rows"]
        if row["contrast"] == "multi_minus_global"
        and row["assumed_paired_effect_sd_random_z"] == 0.5
    )
    assert global_half_sd["approximate_power_at_floor"] < 0.5

    historical_artifact = json.loads(
        (
            ROOT / "experiments/multi_island_hard/threshold_v6_sensitivity_diagnostics.json"
        ).read_text()
    )
    historical_extreme = next(
        row for row in historical_artifact["designs"] if row["design"] == "extreme_extension"
    )
    assert historical_extreme["blocks"] == 24
    assert payload != historical_artifact


@pytest.mark.parametrize(
    "kwargs",
    [
        {"effect": 0, "paired_effect_sd": 1, "blocks": 24, "cells": 25},
        {"effect": 1, "paired_effect_sd": 0, "blocks": 24, "cells": 25},
        {"effect": 1, "paired_effect_sd": 1, "blocks": 1, "cells": 25},
    ],
)
def test_v6_sensitivity_rejects_invalid_inputs(kwargs: dict[str, float | int]) -> None:
    from experiments.multi_island_hard import diagnose_threshold_v6_sensitivity as diagnostic

    with pytest.raises(ValueError):
        diagnostic.approximate_power(**kwargs)
