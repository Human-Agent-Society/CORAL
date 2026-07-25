from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v6_construct_registration_binds_blind_sources() -> None:
    directory = ROOT / "experiments/multi_island_hard"
    registration = json.loads((directory / "threshold_v6_construct_registration.json").read_text())
    assert registration["phase_map_raw_absent_at_registration"] is True
    assert registration["construct_output_absent_at_registration"] is True
    for filename, expected in registration["artifacts"].items():
        observed = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
        assert observed == expected


def test_v6_registered_construct_artifact_audits_and_passes() -> None:
    from experiments.multi_island_hard import diagnose_threshold_v6_construct as diagnostic

    artifact = json.loads(
        (ROOT / "experiments/multi_island_hard/threshold_v6_construct_diagnostics.json").read_text()
    )
    assert artifact["fully_registered_run"] is True
    assert diagnostic.audit(artifact, require_registered=True) == []
    assert len(artifact["rugged_landscapes"]) == 24 * 5
    assert artifact["construct_gates"]["construct_validity_passes"] is True


def test_v6_construct_reduced_run_is_deterministic_and_audits() -> None:
    from experiments.multi_island_hard import diagnose_threshold_v6_construct as diagnostic

    first = diagnostic.run_diagnostics(blocks=2, samples=16, max_workers=1)
    second = diagnostic.run_diagnostics(blocks=2, samples=16, max_workers=1)
    assert first == second
    assert first["fully_registered_run"] is False
    assert diagnostic.audit(first, require_registered=False) == []
    assert len(first["rugged_landscapes"]) == 10


def test_v6_construct_audit_rejects_seed_and_grid_drift() -> None:
    from experiments.multi_island_hard import diagnose_threshold_v6_construct as diagnostic

    payload = diagnostic.run_diagnostics(blocks=2, samples=16, max_workers=1)
    wrong_seed = copy.deepcopy(payload)
    wrong_seed["rugged_landscapes"][0]["seed_sha256"] = "0" * 64
    assert any(
        "unexpected seed hash" in error
        for error in diagnostic.audit(wrong_seed, require_registered=False)
    )

    missing = copy.deepcopy(payload)
    missing["rugged_landscapes"].pop()
    assert any(
        "matrix mismatch" in error for error in diagnostic.audit(missing, require_registered=False)
    )


def test_v6_smooth_construct_grid_spans_severe_and_solvable_scales() -> None:
    from experiments.multi_island_hard import diagnose_threshold_v6_construct as diagnostic

    rows = diagnostic.smooth_scale_rows()
    ratios = [row["budget_over_n_squared"] for row in rows]
    assert min(ratios) <= 0.001
    assert max(ratios) >= 1.0
    assert all(row["strict_one_bit_local_optima"] == 1 for row in rows)
    assert all(row["unique_global_optimum"] is True for row in rows)


def test_v6_construct_gate_requires_ordered_and_blockwise_separation() -> None:
    from experiments.multi_island_hard import diagnose_threshold_v6_construct as diagnostic
    from experiments.multi_island_hard import run_threshold_v6_phase_map as phase

    rows = []
    correlations = {8: 0.95, 16: 0.90, 32: 0.84, 64: 0.75, 128: 0.65}
    for block in range(phase.REGISTERED_BLOCKS):
        for k in phase.RUGGED_K_VALUES:
            rows.append(
                {
                    "block": block,
                    "k": k,
                    "one_bit_autocorrelation": correlations[k],
                    "mean_absolute_neighbour_delta_random_z": 1.0,
                    "neighbour_delta_sd_random_z": 1.0,
                }
            )
    payload = {
        "blocks": phase.REGISTERED_BLOCKS,
        "smooth_scale": diagnostic.smooth_scale_rows(),
        "rugged_landscapes": rows,
    }
    assert diagnostic.construct_gates(payload)["construct_validity_passes"] is True

    for row in rows:
        if row["k"] == 8:
            row["one_bit_autocorrelation"] = 0.60
    gates = diagnostic.construct_gates(payload)
    assert gates["rugged_mean_autocorrelation_strictly_decreases_with_k"] is False
    assert gates["construct_validity_passes"] is False
