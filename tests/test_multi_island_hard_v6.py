from __future__ import annotations

import copy

import pytest


def test_v6_seeds_are_unique_and_disjoint_from_prior_experiments() -> None:
    from experiments.multi_island_hard import run_threshold_v6_phase_map as runner

    seeds = tuple(runner.phase_seed(block) for block in range(runner.REGISTERED_BLOCKS))
    runner.validate_seed_isolation(seeds)
    assert len(set(map(runner.seed_sha256, seeds))) == runner.REGISTERED_BLOCKS


def test_v6_smooth_is_deterministic_and_topology_paired() -> None:
    from experiments.multi_island_hard import run_threshold_v6_phase_map as runner

    common = {
        "family": "smooth",
        "difficulty": 32,
        "budget": 64,
        "block": 0,
        "seed": runner.phase_seed(0),
        "policy_seed": runner.phase_policy_seed(0),
    }
    global_item = runner.WorkItem(**common, condition="global_8")
    assert runner.simulate_smooth(global_item) == runner.simulate_smooth(global_item)
    for condition in runner.CONDITIONS:
        result = runner.simulate_smooth(runner.WorkItem(**common, condition=condition))
        assert 0 <= result["best_prefix"] <= 32
        assert result["best_score"] == result["best_prefix"] / 32


def test_v6_reduced_phase_map_audits_and_analyzes() -> None:
    from experiments.multi_island_hard import analyze_threshold_v6_phase_map as analyzer
    from experiments.multi_island_hard import run_threshold_v6_phase_map as runner

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
    assert result["smooth_decision"]["tested_cells"] == 1

    missing = copy.deepcopy(payload)
    missing["rows"].pop()
    with pytest.raises(ValueError, match="missing 1 topology triplets"):
        analyzer.analyze(missing, require_registered=False)

    wrong_seed = copy.deepcopy(payload)
    wrong_seed["rows"][0]["seed_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="unexpected held-out seed hash"):
        analyzer.analyze(wrong_seed, require_registered=False)


def test_v6_registered_configuration_is_exact() -> None:
    from experiments.multi_island_hard import run_threshold_v6_phase_map as runner

    assert runner.registered_configuration(
        smooth_sizes=runner.SMOOTH_SIZES,
        rugged_ks=runner.RUGGED_K_VALUES,
        budgets=runner.BUDGETS,
        blocks=runner.REGISTERED_BLOCKS,
        reference_samples=runner.REGISTERED_REFERENCE_SAMPLES,
    )
    assert not runner.registered_configuration(
        smooth_sizes=runner.SMOOTH_SIZES,
        rugged_ks=runner.RUGGED_K_VALUES,
        budgets=runner.BUDGETS[:-1],
        blocks=runner.REGISTERED_BLOCKS,
        reference_samples=runner.REGISTERED_REFERENCE_SAMPLES,
    )


def test_v6_registered_audit_recomputes_the_grid() -> None:
    from experiments.multi_island_hard import analyze_threshold_v6_phase_map as analyzer
    from experiments.multi_island_hard import run_threshold_v6_phase_map as runner

    payload = {
        "schema_version": 1,
        "fully_registered_run": True,
        "conditions": list(runner.CONDITIONS),
        "mutation_policy": runner.MUTATION_POLICY,
        "prior_seed_overlap": False,
        "smooth_sizes": [32],
        "rugged_k_values": [2],
        "budgets": [32],
        "blocks": 2,
        "reference_samples_per_rugged_block": 16,
        "rows": [],
        "rugged_random_references": [],
    }
    errors = analyzer.audit(payload, require_registered=True)
    assert "registered phase-map grid or replication count drifted" in errors


def test_v6_multiplicity_bound_is_at_least_as_strict_as_descriptive() -> None:
    from experiments.multi_island_hard import analyze_threshold_v6_phase_map as analyzer

    values = [-0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    descriptive_low, _ = analyzer.bootstrap_mean_interval(
        values,
        label="v6-descriptive",
        lower_probability=0.025,
        repetitions=2_000,
    )
    controlled_low, _ = analyzer.bootstrap_mean_interval(
        values,
        label="v6-controlled",
        lower_probability=0.001,
        repetitions=2_000,
    )
    assert controlled_low <= descriptive_low
