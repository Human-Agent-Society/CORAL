from __future__ import annotations

import math

import pytest


def test_v6_sensitivity_power_increases_with_effect_and_blocks() -> None:
    from experiments.multi_island_hard import diagnose_threshold_v6_sensitivity as diagnostic

    common = {"paired_effect_sd": 0.5, "cells": 25}
    baseline = diagnostic.approximate_power(effect=0.25, blocks=24, **common)
    assert diagnostic.approximate_power(effect=0.5, blocks=24, **common) > baseline
    assert diagnostic.approximate_power(effect=0.25, blocks=48, **common) > baseline


def test_v6_sensitivity_mde_and_required_blocks_are_consistent() -> None:
    from experiments.multi_island_hard import diagnose_threshold_v6_sensitivity as diagnostic

    for cells in (12, 25):
        for paired_effect_sd in diagnostic.PAIRED_EFFECT_SD_GRID:
            mde = diagnostic.minimum_detectable_effect(
                paired_effect_sd=paired_effect_sd,
                blocks=diagnostic.BLOCKS,
                cells=cells,
            )
            power = diagnostic.approximate_power(
                effect=mde,
                paired_effect_sd=paired_effect_sd,
                blocks=diagnostic.BLOCKS,
                cells=cells,
            )
            assert math.isclose(power, diagnostic.TARGET_POWER, abs_tol=1e-12)

            blocks = diagnostic.required_blocks(
                effect=0.25,
                paired_effect_sd=paired_effect_sd,
                cells=cells,
            )
            assert (
                diagnostic.approximate_power(
                    effect=0.25,
                    paired_effect_sd=paired_effect_sd,
                    blocks=blocks,
                    cells=cells,
                )
                >= diagnostic.TARGET_POWER
            )


def test_v6_sensitivity_artifact_has_both_frozen_designs() -> None:
    from experiments.multi_island_hard import diagnose_threshold_v6_sensitivity as diagnostic

    payload = diagnostic.run_diagnostics()
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
