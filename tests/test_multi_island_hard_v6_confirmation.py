from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_confirmation_selector_prefers_strongest_joint_eligible_cell() -> None:
    from experiments.multi_island_hard import select_threshold_v6_extreme_confirmation as selector

    rows = [
        {
            "k": 32,
            "budget": 16384,
            "discovery_effect_margin_random_z": 0.02,
            "discovery_progress_margin_random_z": 0.5,
            "discovery_point_gate_eligible": True,
        },
        {
            "k": 64,
            "budget": 32768,
            "discovery_effect_margin_random_z": 0.08,
            "discovery_progress_margin_random_z": 0.2,
            "discovery_point_gate_eligible": True,
        },
        {
            "k": 96,
            "budget": 65536,
            "discovery_effect_margin_random_z": 0.5,
            "discovery_progress_margin_random_z": 0.5,
            "discovery_point_gate_eligible": False,
        },
    ]
    selected, reason = selector.choose_candidate(rows)
    assert (selected["k"], selected["budget"]) == (64, 32768)
    assert reason.startswith("maximum_joint_effect_margin")


def test_confirmation_selector_has_deterministic_fallback() -> None:
    from experiments.multi_island_hard import select_threshold_v6_extreme_confirmation as selector

    rows = [
        {
            "k": 32,
            "budget": 16384,
            "discovery_effect_margin_random_z": -0.2,
            "discovery_progress_margin_random_z": 0.4,
            "discovery_point_gate_eligible": False,
        },
        {
            "k": 64,
            "budget": 32768,
            "discovery_effect_margin_random_z": -0.1,
            "discovery_progress_margin_random_z": 0.1,
            "discovery_point_gate_eligible": False,
        },
    ]
    selected, reason = selector.choose_candidate(rows)
    assert (selected["k"], selected["budget"]) == (64, 32768)
    assert reason.endswith("fallback")


def test_confirmation_seeds_are_fresh_and_unique() -> None:
    from experiments.multi_island_hard import run_threshold_v6_extreme_confirmation as runner
    from experiments.multi_island_hard import select_threshold_v6_extreme_confirmation as selector

    seeds = tuple(runner.confirmation_seed(block) for block in range(selector.CONFIRMATION_BLOCKS))
    runner.validate_seed_isolation(seeds)
    assert len(set(map(runner.seed_sha256, seeds))) == selector.CONFIRMATION_BLOCKS


def test_confirmation_reduced_run_resumes_audits_and_analyzes(tmp_path: Path) -> None:
    from experiments.multi_island_hard import analyze_threshold_v6_extreme_confirmation as analyzer
    from experiments.multi_island_hard import run_threshold_v6_extreme_confirmation as runner

    arguments = {
        "k": 2,
        "budget": 64,
        "blocks": 3,
        "reference_samples": 16,
        "max_workers": 1,
        "checkpoint": tmp_path / "confirmation-checkpoint.json",
        "checkpoint_every": 1,
        "discovery_source_sha256": "discovery-test-hash",
        "selection_file_sha256": "selection-test-hash",
        "fully_registered_run": False,
    }
    first = runner.run_resumable(**arguments)
    second = runner.run_resumable(**arguments)
    assert first == second
    assert analyzer.audit(first, require_registered=False) == []
    result = analyzer.analyze(
        first,
        require_registered=False,
        bootstrap_repetitions=2_000,
    )
    assert result["audit_passes"] is True
    assert set(result["contrasts"]) == {
        "multi_minus_global",
        "multi_minus_partition",
    }
    assert result["bootstrap_repetitions"] == 2_000

    missing = copy.deepcopy(first)
    missing["rows"].pop()
    with pytest.raises(ValueError, match="block matrix is incomplete"):
        analyzer.analyze(
            missing,
            require_registered=False,
            bootstrap_repetitions=100,
        )


def test_confirmation_checkpoint_rejects_configuration_drift(tmp_path: Path) -> None:
    from experiments.multi_island_hard import run_threshold_v6_extreme_confirmation as runner

    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": runner.CHECKPOINT_SCHEMA_VERSION,
                "configuration": {"wrong": True},
                "expected_items": 0,
                "completed_items": 0,
                "complete": False,
                "completed": {},
            }
        )
    )
    items = runner.work_items(k=2, budget=32, blocks=2)
    expected = runner.configuration(
        k=2,
        budget=32,
        blocks=2,
        reference_samples=16,
        discovery_source_sha256="discovery",
        selection_file_sha256="selection",
    )
    with pytest.raises(ValueError, match="configuration drifted"):
        runner.load_checkpoint(
            checkpoint,
            expected_configuration=expected,
            items=items,
        )


def test_confirmation_sensitivity_covers_registered_dispersion_range() -> None:
    from experiments.multi_island_hard import (
        diagnose_threshold_v6_confirmation_sensitivity as diagnostic,
    )

    payload = diagnostic.run_diagnostics()
    assert payload["blocks"] == 192
    assert payload["design_gate"]["minimum_power_at_target_surplus"] >= 0.8
    assert len(payload["rows"]) == 8
    for row in payload["rows"]:
        recomputed = diagnostic.approximate_gate_power(
            true_effect=row["target_true_effect_random_z"],
            practical_floor=row["practical_floor_random_z"],
            paired_effect_sd=row["assumed_paired_effect_sd_random_z"],
            blocks=payload["blocks"],
        )
        assert math.isclose(
            recomputed,
            row["approximate_gate_power_at_target_effect"],
            abs_tol=1e-12,
        )

    artifact = json.loads(
        (
            ROOT
            / "experiments/multi_island_hard/threshold_v6_extreme_confirmation_sensitivity.json"
        ).read_text()
    )
    assert artifact == payload


def test_confirmation_registration_binds_blind_sources() -> None:
    directory = ROOT / "experiments/multi_island_hard"
    registration_path = directory / "threshold_v6_extreme_registration_v4.json"
    if not registration_path.exists():
        pytest.skip("registration is added after source hashes are frozen")
    registration = json.loads(registration_path.read_text())
    assert registration["discovery_phase_raw_absent_at_registration"] is True
    assert registration["confirmation_selection_absent_at_registration"] is True
    assert registration["confirmation_raw_absent_at_registration"] is True
    assert registration["confirmation_analysis_absent_at_registration"] is True
    assert registration["confirmation_checkpoint_absent_at_registration"] is True
    assert registration["confirmation_blocks"] == 192
    for filename, expected in registration["artifacts"].items():
        observed = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
        assert observed == expected
