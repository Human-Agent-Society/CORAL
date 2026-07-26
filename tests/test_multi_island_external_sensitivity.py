from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_external_validation_sensitivity_matches_registered_artifact() -> None:
    from experiments.multi_island_hard import diagnose_external_validation_sensitivity as audit

    payload = audit.run_diagnostics()
    artifact = json.loads(
        (
            ROOT / "experiments/multi_island_hard/external_validation_sensitivity.json"
        ).read_text()
    )
    assert artifact == payload
    assert {row["design"] for row in payload["designs"]} == set(audit.DESIGNS)


def test_external_confirmations_clear_outcome_free_power_gates() -> None:
    from experiments.multi_island_hard import diagnose_external_validation_sensitivity as audit

    payload = audit.run_diagnostics()
    assert payload["confirmation_design_gates"]["natural"]["minimum_component_power"] >= 0.8
    assert payload["confirmation_design_gates"]["circle"]["minimum_component_power"] >= 0.8

    designs = {row["design"]: row for row in payload["designs"]}
    natural_discovery = next(
        row
        for row in designs["natural_discovery"]["rows"]
        if row["contrast"] == "multi_minus_partition"
        and row["assumed_paired_effect_sd"] == 0.5
    )
    natural_confirmation = next(
        row
        for row in designs["natural_fresh_confirmation"]["rows"]
        if row["contrast"] == "multi_minus_partition"
        and row["assumed_paired_effect_sd"] == 0.5
    )
    assert natural_discovery["approximate_gate_power_at_target_effect"] < 0.25
    assert natural_confirmation["approximate_gate_power_at_target_effect"] >= 0.8


def test_external_sensitivity_required_blocks_are_consistent() -> None:
    from experiments.multi_island_hard import diagnose_external_validation_sensitivity as audit

    payload = audit.run_diagnostics()
    for design in payload["designs"]:
        alpha = float(design["one_sided_alpha_each_required_component"])
        for row in design["rows"]:
            required = int(row["blocks_required_for_80pct_gate_power"])
            power = audit.approximate_gate_power(
                true_effect=float(row["target_true_effect"]),
                practical_floor=float(row["practical_floor"]),
                paired_effect_sd=float(row["assumed_paired_effect_sd"]),
                blocks=required,
                one_sided_alpha=alpha,
            )
            assert power >= audit.TARGET_POWER
            if required > 2:
                previous = audit.approximate_gate_power(
                    true_effect=float(row["target_true_effect"]),
                    practical_floor=float(row["practical_floor"]),
                    paired_effect_sd=float(row["assumed_paired_effect_sd"]),
                    blocks=required - 1,
                    one_sided_alpha=alpha,
                )
                assert previous < audit.TARGET_POWER
            assert math.isfinite(power)


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "true_effect": 0.0,
            "practical_floor": 0.1,
            "paired_effect_sd": 0.5,
            "blocks": 8,
            "one_sided_alpha": 0.05,
        },
        {
            "true_effect": 0.2,
            "practical_floor": 0.1,
            "paired_effect_sd": 0.0,
            "blocks": 8,
            "one_sided_alpha": 0.05,
        },
    ],
)
def test_external_sensitivity_rejects_invalid_inputs(kwargs: dict[str, float | int]) -> None:
    from experiments.multi_island_hard import diagnose_external_validation_sensitivity as audit

    with pytest.raises(ValueError):
        audit.approximate_gate_power(**kwargs)


def test_external_validation_registration_binds_blind_design() -> None:
    directory = ROOT / "experiments/multi_island_hard"
    path = directory / "external_validation_confirmation_registration.json"
    if not path.exists():
        pytest.skip("registration is frozen after source hashes are final")
    registration = json.loads(path.read_text())
    assert registration["natural_results_absent_at_registration"] is True
    assert registration["circle_results_absent_at_registration"] is True
    assert registration["natural_confirmation_blocks"] == 40
    assert registration["circle_confirmation_blocks"] == 32
    for filename, expected in registration["artifacts"].items():
        observed = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
        assert observed == expected
