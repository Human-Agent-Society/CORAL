from __future__ import annotations

import copy
import hashlib
import json
import random
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_extreme_registration_binds_blind_sources() -> None:
    directory = ROOT / "experiments/multi_island_hard"
    registration = json.loads((directory / "threshold_v6_extreme_registration.json").read_text())
    assert registration["phase_raw_absent_at_registration"] is True
    assert registration["phase_analysis_absent_at_registration"] is True
    assert registration["construct_output_absent_at_registration"] is True
    assert registration["superseded_by"] == "threshold_v6_extreme_registration_v2.json"


def test_extreme_v2_registration_binds_64_block_sources() -> None:
    directory = ROOT / "experiments/multi_island_hard"
    registration = json.loads((directory / "threshold_v6_extreme_registration_v2.json").read_text())
    assert registration["registered_blocks"] == 64
    assert registration["phase_raw_absent_at_registration"] is True
    assert registration["phase_analysis_absent_at_registration"] is True
    assert registration["construct_v2_output_absent_at_registration"] is True
    assert registration["superseded_by"] == "threshold_v6_extreme_registration_v3.json"


def test_extreme_v3_registration_binds_resumable_sources() -> None:
    directory = ROOT / "experiments/multi_island_hard"
    registration = json.loads((directory / "threshold_v6_extreme_registration_v3.json").read_text())
    assert registration["registered_blocks"] == 64
    assert registration["checkpoint_every_condition_runs"] == 24
    assert registration["supersession_changes_statistical_parameters"] is False
    assert registration["supersession_changes_heldout_seeds"] is False
    assert registration["phase_raw_absent_at_registration"] is True
    assert registration["phase_analysis_absent_at_registration"] is True
    assert registration["checkpoint_absent_at_registration"] is True
    for filename, expected in registration["artifacts"].items():
        observed = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
        assert observed == expected
    for filename, expected in registration["validated_prerequisite_artifacts"].items():
        observed = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
        assert observed == expected


def test_extreme_registered_construct_artifact_audits_and_bridges_original_v6() -> None:
    from experiments.multi_island_hard import diagnose_threshold_v6_extreme_construct as diagnostic

    directory = ROOT / "experiments/multi_island_hard"
    extreme = json.loads(
        (directory / "threshold_v6_extreme_construct_diagnostics.json").read_text()
    )
    original = json.loads((directory / "threshold_v6_construct_diagnostics.json").read_text())
    assert diagnostic.audit(extreme, require_registered=False) == []
    assert extreme["blocks"] == 24
    assert extreme["construct_gates"]["construct_validity_passes"] is True
    assert len(extreme["rugged_landscapes"]) == 24 * 4

    original_bridge = next(
        row["mean_one_bit_autocorrelation"] for row in original["rugged_summary"] if row["k"] == 128
    )
    extreme_bridge = next(
        row["mean_one_bit_autocorrelation"] for row in extreme["rugged_summary"] if row["k"] == 32
    )
    assert abs(original_bridge - extreme_bridge) < 0.08


def test_extreme_v2_registered_construct_artifact_audits_at_64_blocks() -> None:
    from experiments.multi_island_hard import diagnose_threshold_v6_extreme_construct as diagnostic

    artifact = json.loads(
        (
            ROOT
            / "experiments/multi_island_hard/threshold_v6_extreme_construct_diagnostics_v2.json"
        ).read_text()
    )
    assert diagnostic.audit(artifact, require_registered=True) == []
    assert artifact["blocks"] == 64
    assert len(artifact["rugged_landscapes"]) == 64 * 4
    assert artifact["construct_gates"]["rugged_extreme_separated_blocks"] == 64
    assert artifact["construct_gates"]["construct_validity_passes"] is True


def test_extreme_seeds_are_unique_and_disjoint_from_all_prior_data() -> None:
    from experiments.multi_island_hard import run_threshold_v6_extreme_phase as runner

    seeds = tuple(runner.phase_seed(block) for block in range(runner.REGISTERED_BLOCKS))
    runner.validate_seed_isolation(seeds)
    assert len(set(map(runner.seed_sha256, seeds))) == runner.REGISTERED_BLOCKS


def test_extreme_rugged_topology_is_exactly_null_without_imitation() -> None:
    from experiments.multi_island_hard import calibrate_threshold_v3_social as social
    from experiments.multi_island_hard import run_threshold_v6_extreme_phase as runner

    results = {
        condition: social.simulate(
            n=runner.RUGGED_N,
            k=runner.RUGGED_K_VALUES[-1],
            seed=runner.phase_seed(0),
            condition=condition,
            budget=256,
            imitation=0.0,
            policy_seed=runner.phase_policy_seed(0),
            mutation_policy=runner.MUTATION_POLICY,
            migration_selection="elite",
            initial_salt=runner.INITIAL_SALT,
        )
        for condition in runner.CONDITIONS
    }
    for field in (
        "best_score",
        "final_diversity",
        "final_lineages",
        "mean_active_lineages",
        "adoption_attempts",
        "accepted_adoptions",
    ):
        assert len({result[field] for result in results.values()}) == 1


def test_compact_smooth_mutations_match_literal_permuted_leading_ones() -> None:
    from experiments.multi_island_hard import calibrate_threshold_v3_social as social
    from experiments.multi_island_hard import calibrate_threshold_v5_hard_smooth as smooth
    from experiments.multi_island_hard import run_threshold_v6_extreme_phase as runner

    n = 64
    seed = runner.phase_seed(0)
    target = smooth.hidden_target(seed, n)
    order = smooth.hidden_coordinate_order(seed, n)
    candidate = social.initial_candidate("compact-equivalence", n, runner.INITIAL_SALT)
    compact, ranks = runner.make_compact_smooth(
        candidate,
        target=target,
        order=order,
        lineage="equivalence",
    )
    compact_rng = random.Random(9182)
    literal_rng = random.Random(9182)
    for _ in range(100):
        compact = runner.mutate_compact_smooth(
            compact,
            rank_by_coordinate=ranks,
            rng=compact_rng,
        )
        bits = list(candidate)
        for coordinate in social.mutation_indices(
            literal_rng,
            n,
            runner.MUTATION_POLICY,
        ):
            bits[coordinate] = "0" if bits[coordinate] == "1" else "1"
        candidate = "".join(bits)
        assert compact.prefix == smooth.leading_ones(candidate, target, order)


def test_extreme_reduced_phase_map_audits_and_analyzes() -> None:
    from experiments.multi_island_hard import analyze_threshold_v6_extreme_phase as analyzer
    from experiments.multi_island_hard import run_threshold_v6_extreme_phase as runner

    payload = runner.run_phase_map(
        smooth_sizes=(32,),
        rugged_ks=(2,),
        budgets=(32,),
        blocks=2,
        reference_samples=16,
        max_workers=1,
    )
    assert payload["fully_registered_run"] is False
    assert analyzer.audit(payload, require_registered=False) == []
    result = analyzer.analyze(payload, require_registered=False)
    assert result["audit_passes"] is True
    assert result["rugged_decision"]["tested_cells"] == 1
    assert "search_progress_gate" in result["rugged_phase_map"][0]

    missing = copy.deepcopy(payload)
    missing["rows"].pop()
    with pytest.raises(ValueError, match="missing 1 topology triplets"):
        analyzer.analyze(missing, require_registered=False)


def test_extreme_resumable_runner_matches_direct_runner(tmp_path: Path) -> None:
    from experiments.multi_island_hard import run_threshold_v6_extreme_phase as runner
    from experiments.multi_island_hard import run_threshold_v6_extreme_resumable as resumable

    arguments = {
        "smooth_sizes": (32,),
        "rugged_ks": (2,),
        "budgets": (32,),
        "blocks": 2,
        "reference_samples": 16,
        "max_workers": 1,
    }
    direct = runner.run_phase_map(**arguments)
    checkpoint = tmp_path / "checkpoint.json"
    resumed = resumable.run_resumable(
        **arguments,
        checkpoint=checkpoint,
        checkpoint_every=1,
    )
    assert resumed == direct
    assert (
        resumable.run_resumable(
            **arguments,
            checkpoint=checkpoint,
            checkpoint_every=1,
        )
        == direct
    )
    checkpoint_payload = json.loads(checkpoint.read_text())
    assert checkpoint_payload["complete"] is True
    assert checkpoint_payload["completed_items"] == checkpoint_payload["expected_items"]


def test_extreme_resumable_checkpoint_rejects_configuration_drift(tmp_path: Path) -> None:
    from experiments.multi_island_hard import run_threshold_v6_extreme_resumable as resumable

    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": resumable.CHECKPOINT_SCHEMA_VERSION,
                "configuration": {"wrong": True},
                "expected_items": 0,
                "completed_items": 0,
                "complete": False,
                "completed": {},
            }
        )
    )
    items = resumable.work_items(
        smooth_sizes=(32,),
        rugged_ks=(2,),
        budgets=(32,),
        blocks=2,
    )
    expected = resumable.configuration(
        smooth_sizes=(32,),
        rugged_ks=(2,),
        budgets=(32,),
        blocks=2,
        reference_samples=16,
    )
    with pytest.raises(ValueError, match="configuration drifted"):
        resumable.load_checkpoint(
            checkpoint,
            expected_configuration=expected,
            items=items,
        )


def test_extreme_registered_configuration_is_exact() -> None:
    from experiments.multi_island_hard import run_threshold_v6_extreme_phase as runner

    assert runner.registered_configuration(
        smooth_sizes=runner.SMOOTH_SIZES,
        rugged_ks=runner.RUGGED_K_VALUES,
        budgets=runner.BUDGETS,
        blocks=runner.REGISTERED_BLOCKS,
        reference_samples=runner.REGISTERED_REFERENCE_SAMPLES,
    )
    assert not runner.registered_configuration(
        smooth_sizes=runner.SMOOTH_SIZES,
        rugged_ks=runner.RUGGED_K_VALUES[:-1],
        budgets=runner.BUDGETS,
        blocks=runner.REGISTERED_BLOCKS,
        reference_samples=runner.REGISTERED_REFERENCE_SAMPLES,
    )


def test_extreme_progress_floor_beats_iid_random_search_and_grows_with_budget() -> None:
    from experiments.multi_island_hard import analyze_threshold_v6_extreme_phase as analyzer

    floors = [analyzer.iid_random_max_floor_z(budget) for budget in (16384, 32768, 65536)]
    assert floors == sorted(floors)
    assert floors[0] > 4.0
    assert all(floor - analyzer.RANDOM_SEARCH_MARGIN_Z > 3.5 for floor in floors)


def test_extreme_construct_reduced_run_is_deterministic_and_audits() -> None:
    from experiments.multi_island_hard import diagnose_threshold_v6_extreme_construct as diagnostic

    first = diagnostic.run_diagnostics(blocks=2, samples=16, max_workers=1)
    second = diagnostic.run_diagnostics(blocks=2, samples=16, max_workers=1)
    assert first == second
    assert first["fully_registered_run"] is False
    assert diagnostic.audit(first, require_registered=False) == []
    assert len(first["rugged_landscapes"]) == 8


def test_extreme_construct_gate_requires_an_actual_low_correlation_endpoint() -> None:
    from experiments.multi_island_hard import diagnose_threshold_v6_extreme_construct as diagnostic
    from experiments.multi_island_hard import run_threshold_v6_extreme_phase as phase

    correlations = {32: 0.75, 64: 0.50, 96: 0.24, 120: 0.08}
    rows = [
        {
            "block": block,
            "k": k,
            "one_bit_autocorrelation": correlations[k],
            "mean_absolute_neighbour_delta_random_z": 1.0,
            "neighbour_delta_sd_random_z": 1.0,
        }
        for block in range(phase.REGISTERED_BLOCKS)
        for k in phase.RUGGED_K_VALUES
    ]
    payload = {
        "blocks": phase.REGISTERED_BLOCKS,
        "smooth_scale": diagnostic.smooth_scale_rows(),
        "rugged_landscapes": rows,
    }
    assert diagnostic.construct_gates(payload)["construct_validity_passes"] is True
    for row in rows:
        if row["k"] == 120:
            row["one_bit_autocorrelation"] = 0.20
    gates = diagnostic.construct_gates(payload)
    assert gates["rugged_extremes_separate"] is False
    assert gates["construct_validity_passes"] is False
