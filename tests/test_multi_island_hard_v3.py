"""Tests for the N=256 social-learning phase study."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from experiments.multi_island_hard.behavior_metrics import behavior_metrics

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments/multi_island_hard"
TASK_DIR = EXPERIMENT / "tasks/institutional_landscape"


def test_v3_tasks_are_harder_paired_held_out_landscapes() -> None:
    from coral.config import CoralConfig

    smooth = json.loads((TASK_DIR / "taskdata/smooth256_replicated_v3.json").read_text())
    rugged = json.loads((TASK_DIR / "taskdata/rugged256_k32_replicated_v3.json").read_text())
    calibration = json.loads((EXPERIMENT / "threshold_v3_calibration_landscapes.json").read_text())
    assert (smooth["n"], smooth["k"]) == (256, 0)
    assert (rugged["n"], rugged["k"]) == (256, 32)
    assert smooth["seeds"] == rugged["seeds"]
    assert len(smooth["seeds"]) == 8
    assert set(smooth["seeds"]).isdisjoint(calibration["seeds"])
    for filename in (
        "task_smooth256_replicated_v3.yaml",
        "task_rugged256_k32_replicated_v3.yaml",
    ):
        config = CoralConfig.from_yaml(TASK_DIR / filename)
        assert config.agents.count == 8
        assert config.agents.timeout == 240
        assert config.agents.sandbox.allowed_domains == ["api.appintheloop.com"]


def test_social_calibration_has_exact_zero_imitation_null() -> None:
    from experiments.multi_island_hard import calibrate_threshold_v3_social as calibration

    rows = [
        calibration.simulate(
            n=64,
            k=8,
            seed="a" * 64,
            condition=condition,
            budget=256,
            imitation=0.0,
            policy_seed=7,
        )
        for condition in calibration.CONDITIONS
    ]
    assert len({row["best_score"] for row in rows}) == 1
    assert len({row["final_diversity"] for row in rows}) == 1
    assert all(row["final_lineages"] == 8 for row in rows)
    assert [row["migration_cycles"] for row in rows] == [0, 0, 3, 3]


def test_social_calibration_supports_versioned_paired_initial_candidates() -> None:
    from experiments.multi_island_hard import calibrate_threshold_v3_social as calibration

    v3 = calibration.initial_candidate("captain-nemo", 512)
    v4 = calibration.initial_candidate("captain-nemo", 512, "coral-threshold-v4")
    assert len(v3) == len(v4) == 512
    assert v3 != v4
    assert v3 == calibration.initial_candidate("captain-nemo", 512)


def test_social_calibration_activates_lineage_collapse_only_with_diffusion() -> None:
    from experiments.multi_island_hard import calibrate_threshold_v3_social as calibration

    values = {}
    for condition in ("global_8", "partition_4", "multi_island_4"):
        values[condition] = calibration.simulate(
            n=64,
            k=8,
            seed="a" * 64,
            condition=condition,
            budget=512,
            imitation=1.0,
            policy_seed=7,
        )
    assert values["global_8"]["final_lineages"] == 1
    assert values["partition_4"]["final_lineages"] == 4
    assert (
        values["multi_island_4"]["mean_active_lineages"]
        > values["global_8"]["mean_active_lineages"]
    )


def test_social_calibration_exposes_operator_and_migration_falsification_controls() -> None:
    from experiments.multi_island_hard import calibrate_threshold_v3_social as calibration

    common = {
        "n": 64,
        "k": 8,
        "seed": "b" * 64,
        "condition": "multi_island_4",
        "budget": 256,
        "imitation": 1.0,
        "policy_seed": 11,
    }
    mutation_scores = {
        policy: calibration.simulate(**common, mutation_policy=policy)["best_score"]
        for policy in calibration.MUTATION_POLICIES
    }
    migration_scores = {
        selection: calibration.simulate(**common, migration_selection=selection)["best_score"]
        for selection in calibration.MIGRATION_SELECTIONS
    }
    assert set(mutation_scores) == set(calibration.MUTATION_POLICIES)
    assert set(migration_scores) == set(calibration.MIGRATION_SELECTIONS)
    assert len(set(mutation_scores.values())) > 1


def test_v3_robustness_uses_landscapes_as_inference_unit() -> None:
    from experiments.multi_island_hard.calibrate_threshold_v3_robustness import cluster_summary

    values = {"landscape-a": [1.0, 3.0], "landscape-b": [-1.0, 1.0]}
    result = cluster_summary(values, bootstrap_repetitions=200, bootstrap_seed=7)
    assert result["landscape_clusters"] == 2
    assert result["policy_runs_per_landscape"] == 2
    assert result["paired_runs"] == 4
    assert result["mean_random_z_difference"] == 1.0
    assert result["per_landscape_mean_random_z"] == [2.0, 0.0]


def test_v3_calibration_selects_first_stable_full_diffusion_boundary() -> None:
    data = json.loads((EXPERIMENT / "threshold_v3_social_calibration.json").read_text())
    decision = data["decision"]
    assert decision["selection_imitation"] == 1.0
    assert decision["selected_rugged_k"] == 32
    assert decision["selected_anchor_budget"] == 4096
    selected = next(
        row
        for row in data["summary"]
        if row["k"] == 32
        and row["budget"] == 4096
        and row["imitation"] == 1.0
        and row["contrast"] == "multi_island_4_minus_global_8"
    )
    assert selected["phase_gate_passes"] is True
    assert selected["random_z_ci_low"] > 0
    assert selected["rugged_minus_smooth_random_z_ci_low"] > 0


def test_v3_phase_map_falsifies_universal_island_advantage() -> None:
    data = json.loads((EXPERIMENT / "threshold_v3_social_phase_map.json").read_text())
    assert data["imitation_levels"] == [0.0, 0.25, 0.5, 0.75, 1.0]
    rugged = [
        row
        for row in data["summary"]
        if row["k"] == 32 and row["contrast"] == "multi_island_4_minus_global_8"
    ]
    assert all(
        row["random_z_difference"] == 0 and row["random_z_ci_low"] == 0
        for row in rugged
        if row["imitation"] == 0
    )
    assert not any(row["phase_gate_passes"] for row in rugged if row["imitation"] == 0.75)
    anchor = next(row for row in rugged if row["imitation"] == 1.0 and row["budget"] == 4096)
    assert anchor["phase_gate_passes"] is True
    assert anchor["random_z_ci_low"] > 0


def test_v3_out_of_selection_audit_rejects_universal_and_elite_claims() -> None:
    data = json.loads((EXPERIMENT / "threshold_v3_robustness.json").read_text())
    assert data["inference_unit"].startswith("landscape seed")
    assert data["decision"]["is_universal_over_tested_mutations"] is False
    assert data["decision"]["elite_selection_identified"] is False
    assert data["mutation_robustness"]["one_bit"]["cluster_bootstrap_ci_low"] > 0
    assert data["mutation_robustness"]["four_bit"]["cluster_bootstrap_ci_high"] < 0
    for selection in ("elite", "fixed_identity", "worst"):
        contrast = data["migration_selection_robustness"][selection][
            "multi_island_4_minus_partition_4"
        ]
        assert contrast["cluster_bootstrap_ci_low"] <= 0 <= contrast[
            "cluster_bootstrap_ci_high"
        ]


def test_v4_scale_rule_separates_boundary_from_migration_threshold() -> None:
    from experiments.multi_island_hard import calibrate_threshold_v4_scale as calibration

    rows = []
    for mutation in calibration.MUTATION_POLICIES:
        for contrast, mean, low in (
            ("multi_island_4_minus_global_8", 0.40, 0.20),
            ("multi_island_4_minus_partition_4", 0.15, 0.05),
            ("rugged_minus_smooth_multi_island_4_minus_global_8", 0.35, 0.10),
        ):
            rows.append(
                {
                    "k": 32,
                    "budget": 8192,
                    "mutation": mutation,
                    "contrast": contrast,
                    "mean_random_z_difference": mean,
                    "cluster_bootstrap_ci_low": low,
                }
            )
    decision = calibration.select_threshold(rows, k_values=(0, 32), budgets=(8192,))
    assert decision["earliest_boundary_threshold"] == {"k": 32, "budget": 8192}
    assert decision["earliest_migration_threshold"] == {"k": 32, "budget": 8192}
    assert decision["earliest_four_bit_generalization_threshold"] == {
        "k": 32,
        "budget": 8192,
    }

    failed_row = next(
        row
        for row in rows
        if row["mutation"] == "broader"
        and row["contrast"] == "multi_island_4_minus_partition_4"
    )
    failed_row["cluster_bootstrap_ci_low"] = -0.01
    decision = calibration.select_threshold(rows, k_values=(0, 32), budgets=(8192,))
    assert decision["earliest_boundary_threshold"] == {"k": 32, "budget": 8192}
    assert decision["earliest_migration_threshold"] is None


def test_v4_scale_uses_harder_dimension_and_operator_stress_test() -> None:
    from experiments.multi_island_hard import calibrate_threshold_v4_scale as calibration

    assert calibration.N == 512
    assert calibration.K_VALUES == (0, 16, 32, 64, 128)
    assert calibration.BUDGETS == (4096, 8192, 16384)
    assert set(calibration.LOCAL_MUTATION_FAMILY) < set(calibration.MUTATION_POLICIES)
    assert "four_bit" in calibration.MUTATION_POLICIES


def test_v4_full_calibration_records_boundary_migration_and_failed_generalization() -> None:
    data = json.loads((EXPERIMENT / "threshold_v4_scale_calibration.json").read_text())
    assert data["fully_registered_run"] is True
    assert len(data["summaries"]) == 168
    assert all(
        row["landscape_clusters"] == 8
        and row["policy_runs_per_landscape"] == 4
        and row["paired_runs"] == 32
        for row in data["summaries"]
    )
    decision = data["decision"]
    assert decision["earliest_boundary_threshold"] == {"k": 32, "budget": 8192}
    assert decision["earliest_migration_threshold"] == {"k": 64, "budget": 16384}
    assert decision["earliest_four_bit_generalization_threshold"] is None


def test_v4_heldout_diagnostics_separate_smooth_and_rugged() -> None:
    data = json.loads((EXPERIMENT / "threshold_v4_diagnostics.json").read_text())
    assert (data["selected_k"], data["selected_budget"]) == (32, 8192)
    assert (data["random_samples"], data["greedy_starts"]) == (1024, 32)
    smooth = [row for row in data["landscapes"] if row["k"] == 0]
    rugged = [row for row in data["landscapes"] if row["k"] == 32]
    assert len(smooth) == len(rugged) == 8
    assert [row["seed_sha256"] for row in smooth] == [
        row["seed_sha256"] for row in rugged
    ]
    assert all(row["reference_is_exact"] and row["greedy_unique_maxima"] == 1 for row in smooth)
    assert all(
        not row["reference_is_exact"] and row["greedy_unique_maxima"] == 32
        for row in rugged
    )
    assert max(row["one_bit_autocorrelation"] for row in rugged) < min(
        row["one_bit_autocorrelation"] for row in smooth
    )


def test_v5_hard_smooth_calibration_avoids_cross_family_z_interaction() -> None:
    data = json.loads(
        (EXPERIMENT / "threshold_v5_hard_smooth_calibration.json").read_text()
    )
    assert data["fully_registered_run"] is True
    assert data["cross_family_standardized_interaction"] is None
    assert "not commensurate" in data["cross_family_interaction_reason"]
    assert data["decision"]["selected_hard_anchor"] == {"k": 64, "budget": 16384}

    local_mutations = set(data["decision"]["required_local_mutation_family"])
    hardness = [
        row
        for row in data["smooth_summaries"]
        if row["contrast"] == "global_hardness_diagnostic"
        and row["mutation"] in local_mutations
    ]
    assert len(hardness) == 9
    assert all(row["exact_solutions"] == 0 for row in hardness)
    assert max(row["max_best_prefix"] for row in hardness) < 128

    smooth_directions = [
        row
        for row in data["smooth_summaries"]
        if row["contrast"] == "multi_island_4_minus_global_8"
        and row["mutation"] in local_mutations
    ]
    assert len(smooth_directions) == 9
    assert all(row["cluster_bootstrap_ci_high"] < 0 for row in smooth_directions)


def test_v5_smooth_diagnostic_proves_topology_without_claiming_agent_oracle() -> None:
    from experiments.multi_island_hard.diagnose_threshold_v5 import smooth_diagnostic

    row = smooth_diagnostic(
        "smooth",
        0,
        "a" * 64,
        n=32,
        samples=128,
        starts=8,
    )
    assert row["family"] == "permuted_leading_ones"
    assert row["strict_one_bit_local_optima"] == 1
    assert row["unique_global_optimum"] is True
    assert row["greedy_reference_score"] == 1.0
    assert "not a performance baseline" in row["oracle_note"]


def test_v5_difficulty_gate_requires_many_rugged_maxima_and_separation() -> None:
    from experiments.multi_island_hard import diagnose_threshold_v5 as diagnostics

    smooth_rows = [
        {
            "family": "permuted_leading_ones",
            "seed_sha256": str(index),
            "reference_is_exact": True,
            "greedy_unique_maxima": 1,
            "strict_one_bit_local_optima": 1,
            "unique_global_optimum": True,
            "one_bit_autocorrelation": 0.99,
        }
        for index in range(8)
    ]
    rugged_rows = [
        {
            "family": "nk",
            "seed_sha256": str(index),
            "reference_is_exact": False,
            "greedy_unique_maxima": 32,
            "one_bit_autocorrelation": 0.8,
        }
        for index in range(8)
    ]
    gates = diagnostics.difficulty_gates(
        [*smooth_rows, *rugged_rows],
        starts=diagnostics.REGISTERED_GREEDY_STARTS,
    )
    assert gates["heldout_difficulty_passes"] is True

    rugged_rows[0]["greedy_unique_maxima"] = 23
    gates = diagnostics.difficulty_gates(
        [*smooth_rows, *rugged_rows],
        starts=diagnostics.REGISTERED_GREEDY_STARTS,
    )
    assert gates["rugged_multibasin"] is False
    assert gates["heldout_difficulty_passes"] is False


def test_v5_scripted_runner_uses_selected_hard_anchor_and_balanced_quota(
    tmp_path: Path,
) -> None:
    from experiments.multi_island_hard import run_threshold_v5_mechanism as runner

    assert runner.registered_selection() == {"k": 64, "budget": 16384}
    assert runner.seed_contract_errors() == []
    runner.base.EXPECTED_REAL_ATTEMPTS = 256
    command = runner.build_command(
        runner.TASKS[runner.RUGGED_TASKS[64]],
        "multi_island_4",
        tmp_path / "task" / "condition" / "rep-01",
    )
    assert "agents.count=8" in command
    assert f"agents.runtime={runner.SCRIPTED_RUNTIME}" in command
    assert "agents.model=scripted" in command
    assert "agents.timeout=0" in command
    assert "agents.sandbox.allowed_domains=[]" in command
    assert "run.stop.max_real_attempts=256" in command
    assert "run.stop.max_real_attempts_per_agent=32" in command
    assert "islands.migration.every=64" in command
    assert "islands.migration.dest_weighting=round_robin" in command
    assert any("scripted_search.py" in item for item in command)


def test_v5_scripted_runner_separates_smoke_from_confirmatory_ladder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from experiments.multi_island_hard import run_threshold_v5_mechanism as runner

    selection = runner.registered_selection()
    for budget in runner.CONFIRMATORY_BUDGETS:
        monkeypatch.setattr(runner.sys, "argv", ["runner", "--budget", str(budget)])
        runner.enforce_matrix(selection, engineering_smoke=False)

    monkeypatch.setattr(runner.sys, "argv", ["runner", "--budget", "1024"])
    with pytest.raises(SystemExit, match="confirmatory budget"):
        runner.enforce_matrix(selection, engineering_smoke=False)

    monkeypatch.setattr(runner.sys, "argv", ["runner", "--budget", "4096"])
    with pytest.raises(SystemExit, match=r"\[32, 4096\)"):
        runner.enforce_matrix(selection, engineering_smoke=True)


def test_v5_natural_runner_uses_same_anchor_without_scripted_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from experiments.multi_island_hard import run_threshold_v5_natural as runner

    selection = runner.mechanism.registered_selection()
    assert selection == {"k": 64, "budget": 16384}
    assert runner.seed_contract_errors() == []
    monkeypatch.setattr(runner.base, "EXPECTED_REAL_ATTEMPTS", selection["budget"])
    command = runner.build_command(
        runner.TASKS[runner.mechanism.RUGGED_TASKS[selection["k"]]],
        "multi_island_4",
        tmp_path / "task" / "condition" / "rep-01",
    )
    assert "agents.count=8" in command
    assert "agents.runtime=opencode" in command
    assert "agents.model=mafia/glm-5.2" in command
    assert f"agents.runtime_options.role_file={runner.ROLE_FILE}" in command
    assert f"agents.timeout={runner.AGENT_TIMEOUT}" in command
    assert 'agents.sandbox.allowed_domains=["api.appintheloop.com"]' in command
    assert "run.stop.max_real_attempts=16384" in command
    assert "run.stop.max_real_attempts_per_agent=2048" in command
    assert "islands.migration.every=4096" in command
    assert "islands.migration.dest_weighting=round_robin" in command
    assert not any("scripted_search.py" in item for item in command)


def test_v5_natural_runner_rotates_paired_condition_stages() -> None:
    from experiments.multi_island_hard import run_threshold_v5_natural as runner

    tasks = list(runner.TASKS)
    cells = list(runner.latin_square_cells(tasks, list(runner.CONDITIONS), 3))
    orders = []
    for repetition in (1, 2, 3):
        block = [
            condition
            for _spec, condition, observed_repetition in cells
            if observed_repetition == repetition
        ]
        orders.append(block[:: len(tasks)])
        assert all(
            block[index : index + len(tasks)] == [block[index]] * len(tasks)
            for index in range(0, len(block), len(tasks))
        )
    assert orders == [
        ["global_8", "partition_4", "multi_island_4"],
        ["partition_4", "multi_island_4", "global_8"],
        ["multi_island_4", "global_8", "partition_4"],
    ]


def test_v5_natural_analysis_keeps_tasks_and_controls_separate() -> None:
    from experiments.multi_island_hard.analyze_threshold_v5_natural import contrasts

    rows = []
    for task, offset in (("smooth", 0.0), ("rugged", 1.0)):
        for repetition in (1, 2):
            for condition, effect in (
                ("global_8", 0.1),
                ("partition_4", 0.2),
                ("multi_island_4", 0.5),
            ):
                rows.append(
                    {
                        "task": task,
                        "condition": condition,
                        "repetition": repetition,
                        "final_best": offset + effect,
                    }
                )
    output = contrasts(rows)
    assert len(output) == 4
    assert all(row["metric"] == "final_best" for row in output)
    assert {(row["task"], row["contrast"]) for row in output} == {
        (task, f"multi_island_4_minus_{control}")
        for task in ("smooth", "rugged")
        for control in ("global_8", "partition_4")
    }
    assert all(row["paired_repetitions"] == 2 for row in output)


def test_v5_natural_analysis_rejects_roster_matrix_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    from experiments.multi_island_hard import analyze_threshold_v5_natural as analyzer
    from experiments.multi_island_hard import run_threshold_v5_natural as runner

    budget = runner.mechanism.registered_selection()["budget"]
    budget_root = tmp_path / f"budget-{budget}"
    budget_root.mkdir()
    (budget_root / "natural-agent-audit.json").write_text(
        json.dumps(
            {
                "valid_cells": 6,
                "expected_cells": 6,
                "matrix_errors": ["roster drift"],
                "budget": budget,
                "repetitions": 1,
                "cells": [],
            }
        )
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "analyze_threshold_v5_natural.py",
            "--results-root",
            str(tmp_path),
            "--repetitions",
            "1",
        ],
    )
    with pytest.raises(SystemExit, match="complete matching audit"):
        analyzer.main()


def test_v5_natural_decision_requires_practical_random_z_floor() -> None:
    from experiments.multi_island_hard import analyze_threshold_v5_natural as analyzer

    rugged = "rugged"
    rows = [
        {
            "condition": "multi_island_4",
            "post_migration_migrant_submission_events": 1,
        }
        for _ in range(16)
    ]
    paired = []
    for contrast, raw, random_z in (
        ("multi_island_4_minus_global_8", 0.01, 0.30),
        ("multi_island_4_minus_partition_4", 0.005, 0.15),
    ):
        paired.extend(
            [
                {
                    "task": rugged,
                    "contrast": contrast,
                    "metric": "final_best",
                    "paired_repetitions": 8,
                    "mean_difference": raw,
                    "bootstrap_ci_low": raw / 2,
                },
                {
                    "task": rugged,
                    "contrast": contrast,
                    "metric": "random_z_final_best",
                    "paired_repetitions": 8,
                    "mean_difference": random_z,
                    "bootstrap_ci_low": random_z / 2,
                },
            ]
        )
    result = analyzer.decision(rows, paired, rugged_task=rugged, repetitions=8)
    assert result["confirmatory_natural_agent_threshold_passes"] is True

    next(
        row
        for row in paired
        if row["metric"] == "random_z_final_best"
        and row["contrast"] == "multi_island_4_minus_global_8"
    )["mean_difference"] = 0.249
    result = analyzer.decision(rows, paired, rugged_task=rugged, repetitions=8)
    assert result["confirmatory_natural_agent_threshold_passes"] is False


def test_v5_natural_migration_gate_requires_migrant_submission(
    tmp_path: Path,
) -> None:
    from experiments.multi_island_hard.audit_threshold_v5_natural import (
        migration_errors,
    )

    event = {
        "source": "migration",
        "agent_id": "captain-nemo-from-avalon",
        "log_island": "atlantis",
        "timestamp": "2026-07-25T12:00:00+00:00",
    }
    later = {
        "agent_id": "captain-nemo-from-avalon",
        "timestamp": "2026-07-25T12:00:01+00:00",
        "metadata": {"island_id": "atlantis"},
    }
    errors, events, exposed = migration_errors(
        tmp_path,
        "multi_island_4",
        [later],
        [event],
    )
    assert errors == []
    assert (events, exposed) == (1, 1)

    errors, events, exposed = migration_errors(
        tmp_path,
        "multi_island_4",
        [],
        [event],
    )
    assert errors == ["no post-migration migrant submission in destinations=['atlantis']"]
    assert (events, exposed) == (1, 0)


def test_v5_heldout_seeds_are_disjoint_from_mechanism_calibration() -> None:
    calibration = json.loads(
        (EXPERIMENT / "threshold_v5_hard_smooth_calibration.json").read_text()
    )
    heldout = json.loads(
        (
            TASK_DIR
            / "taskdata/smooth512_permuted_leading_ones_replicated_v5.json"
        ).read_text()
    )["seeds"]
    heldout_hashes = {hashlib.sha256(seed.encode()).hexdigest() for seed in heldout}
    assert len(heldout) == len(set(heldout)) == 8
    assert heldout_hashes.isdisjoint(calibration["calibration_seed_sha256"])


def test_v5_mechanism_analysis_keeps_task_contrasts_separate() -> None:
    from experiments.multi_island_hard.analyze_threshold_v5_mechanism import contrasts

    rows = []
    for task, offset in (("smooth", 0.0), ("rugged", 1.0)):
        for repetition in (1, 2):
            for condition, effect in (
                ("global_8", 0.1),
                ("partition_4", 0.2),
                ("multi_island_4", 0.5),
            ):
                rows.append(
                    {
                        "task": task,
                        "condition": condition,
                        "repetition": repetition,
                        "final_best": offset + effect,
                    }
                )
    output = contrasts(rows)
    assert len(output) == 4
    assert {(row["task"], row["contrast"]) for row in output} == {
        (task, f"multi_island_4_minus_{control}")
        for task in ("smooth", "rugged")
        for control in ("global_8", "partition_4")
    }
    assert all(row["paired_repetitions"] == 2 for row in output)


def test_v5_mechanism_decision_requires_hard_smooth_falsification() -> None:
    from experiments.multi_island_hard import analyze_threshold_v5_mechanism as analyzer
    from experiments.multi_island_hard import run_threshold_v5_mechanism as runner

    selection = {"k": 64, "budget": 16384}
    rugged = runner.RUGGED_TASKS[selection["k"]]
    rows = [
        {"task": runner.SMOOTH_TASK, "final_best": 0.25}
        for _ in range(8 * len(runner.CONDITIONS))
    ]
    paired = [
        {
            "task": rugged,
            "contrast": "multi_island_4_minus_global_8",
            "paired_repetitions": 8,
            "bootstrap_ci_low": 0.01,
            "bootstrap_ci_high": 0.03,
            "ladder_simultaneous_ci_low": 0.008,
            "ladder_simultaneous_ci_high": 0.032,
            "mean_random_z_difference": 0.5,
            "random_z_ladder_simultaneous_ci_low": 0.15,
        },
        {
            "task": rugged,
            "contrast": "multi_island_4_minus_partition_4",
            "paired_repetitions": 8,
            "bootstrap_ci_low": 0.005,
            "bootstrap_ci_high": 0.02,
            "ladder_simultaneous_ci_low": 0.003,
            "ladder_simultaneous_ci_high": 0.022,
            "mean_random_z_difference": 0.2,
            "random_z_ladder_simultaneous_ci_low": 0.05,
        },
        {
            "task": runner.SMOOTH_TASK,
            "contrast": "multi_island_4_minus_global_8",
            "paired_repetitions": 8,
            "bootstrap_ci_low": -0.04,
            "bootstrap_ci_high": -0.01,
            "ladder_simultaneous_ci_low": -0.045,
            "ladder_simultaneous_ci_high": -0.005,
        },
    ]
    result = analyzer.decision(
        rows,
        paired,
        budget=selection["budget"],
        repetitions=8,
        selection=selection,
        registered_budget=True,
    )
    assert result["confirmatory_mechanism_threshold_passes"] is True
    assert result["cross_family_effect_pooling"] is False
    assert result["boundary_effect_floor_random_z"] == 0.25
    assert result["migration_effect_floor_random_z"] == 0.10

    paired[2]["bootstrap_ci_high"] = 0.001
    paired[2]["ladder_simultaneous_ci_high"] = 0.002
    result = analyzer.decision(
        rows,
        paired,
        budget=selection["budget"],
        repetitions=8,
        selection=selection,
        registered_budget=True,
    )
    assert result["rugged_beats_global"] is True
    assert result["rugged_beats_partition"] is True
    assert result["hard_smooth_global_beats_multi"] is False
    assert result["confirmatory_mechanism_threshold_passes"] is False

    paired[2]["ladder_simultaneous_ci_high"] = -0.005
    paired[0]["mean_random_z_difference"] = 0.249
    result = analyzer.decision(
        rows,
        paired,
        budget=selection["budget"],
        repetitions=8,
        selection=selection,
        registered_budget=True,
    )
    assert result["rugged_beats_global"] is False
    assert result["confirmatory_mechanism_threshold_passes"] is False

    paired[2]["bootstrap_ci_high"] = -0.01
    result = analyzer.decision(
        rows,
        paired,
        budget=selection["budget"],
        repetitions=8,
        selection=selection,
        registered_budget=False,
    )
    assert result["confirmatory_ready"] is False
    assert result["confirmatory_mechanism_threshold_passes"] is False


def test_v5_integrity_rejects_an_invalidated_budget_root(tmp_path: Path) -> None:
    from experiments.multi_island_hard import audit_threshold_v5_mechanism as audit

    budget_root = tmp_path / "budget-256"
    budget_root.mkdir()
    audit.require_budget_not_invalidated(budget_root)
    (budget_root / "experiment-invalid.json").write_text(
        json.dumps({"reason": "superseded task design"}) + "\n"
    )
    with pytest.raises(SystemExit, match="budget root is invalidated"):
        audit.require_budget_not_invalidated(budget_root)


def test_v5_ladder_summary_requires_complete_registered_slices(tmp_path: Path) -> None:
    from experiments.multi_island_hard import summarize_threshold_v5_ladder as summary

    decisions = {4096: False, 8192: False, 16384: True}
    for budget, passes in decisions.items():
        root = tmp_path / f"budget-{budget}"
        root.mkdir()
        (root / "scripted-mechanism-audit.json").write_text(
            json.dumps(
                {
                    "registered_budget": True,
                    "valid_cells": 48,
                    "expected_cells": 48,
                    "matrix_errors": [],
                    "budget": budget,
                    "repetitions": 8,
                }
            )
        )
        (root / "scripted-mechanism-analysis.json").write_text(
            json.dumps(
                {
                    "budget": budget,
                    "repetitions": 8,
                    "decision": {
                        "confirmatory_ready": True,
                        "rugged_beats_global": passes,
                        "rugged_beats_partition": passes,
                        "hard_smooth_global_beats_multi": True,
                        "hard_smooth_unsolved": True,
                        "confirmatory_mechanism_threshold_passes": passes,
                    },
                }
            )
        )
    result = summary.summarize(
        tmp_path,
        budgets=(4096, 8192, 16384),
        repetitions=8,
    )
    assert result["errors"] == []
    assert result["earliest_supported_multi_island_threshold"] == 16384

    (tmp_path / "budget-8192/scripted-mechanism-analysis.json").unlink()
    result = summary.summarize(
        tmp_path,
        budgets=(4096, 8192, 16384),
        repetitions=8,
    )
    assert result["earliest_supported_multi_island_threshold"] == 16384
    assert result["errors"]


def test_v4_candidate_tasks_are_paired_and_disjoint_from_calibration() -> None:
    from coral.config import CoralConfig
    from experiments.multi_island_hard import calibrate_threshold_v4_scale as calibration

    filenames = {
        0: "smooth512_replicated_v4.json",
        16: "rugged512_k16_replicated_v4.json",
        32: "rugged512_k32_replicated_v4.json",
        64: "rugged512_k64_replicated_v4.json",
        128: "rugged512_k128_replicated_v4.json",
    }
    bundles = {
        k: json.loads((TASK_DIR / "taskdata" / filename).read_text())
        for k, filename in filenames.items()
    }
    paired_seeds = bundles[0]["seeds"]
    assert len(paired_seeds) == 8
    assert paired_seeds == [calibration.heldout_seed(index) for index in range(8)]
    for k, bundle in bundles.items():
        assert (bundle["n"], bundle["k"]) == (512, k)
        assert bundle["seeds"] == paired_seeds
    assert set(paired_seeds).isdisjoint(
        calibration.generated_seed(index)
        for index in range(calibration.CALIBRATION_LANDSCAPES)
    )

    configs = ["task_smooth512_replicated_v4.yaml"] + [
        f"task_rugged512_k{k}_replicated_v4.yaml" for k in (16, 32, 64, 128)
    ]
    for filename in configs:
        config = CoralConfig.from_yaml(TASK_DIR / filename)
        assert config.agents.count == 8
        assert config.agents.timeout == 240
        assert config.run.stop.max_real_attempts == 16384
        assert config.agents.sandbox.allowed_domains == ["api.appintheloop.com"]
        assert config.workspace.seed_path is None


def test_v4_seed_contract_and_initializer_match_analyzer() -> None:
    import runpy

    from experiments.multi_island_hard import analyze_threshold_v2 as analyzer
    from experiments.multi_island_hard import run_threshold_v4 as runner

    assert runner.seed_contract_errors() == []
    initializer = runpy.run_path(str(TASK_DIR / "seed_v4" / "initialize_candidate.py"))
    actual = initializer["initial_candidate"]("captain-nemo-from-atlantis")
    previous_salt = analyzer.INITIAL_SALT
    analyzer.INITIAL_SALT = "coral-threshold-v4"
    try:
        expected = analyzer.initial_candidate("captain-nemo-from-atlantis", 512)
    finally:
        analyzer.INITIAL_SALT = previous_salt
    assert len(actual) == 512
    assert actual == expected


def test_v4_project_creation_does_not_overlay_legacy_seed(
    tmp_path: Path, monkeypatch
) -> None:
    from coral.config import CoralConfig
    from coral.workspace.project import create_project
    from experiments.multi_island_hard import run_threshold_v4 as runner

    config_path = TASK_DIR / "task_smooth512_replicated_v4.yaml"
    config = CoralConfig.from_yaml(config_path)
    config.task_dir = TASK_DIR
    config.grader.setup = []
    config.grader.private = []
    config.workspace.results_dir = str(tmp_path / "results")
    config.workspace.run_dir = str(tmp_path / "run")
    monkeypatch.chdir(TASK_DIR)

    paths = create_project(config, config_dir=TASK_DIR)

    assert len(runner._literal_candidate(paths.repo_dir / "candidate.py")) == 512
    assert (paths.repo_dir / "initialize_candidate.py").is_file()


def test_v4_runner_refuses_reduced_or_missing_calibration(tmp_path: Path) -> None:
    from experiments.multi_island_hard import run_threshold_v4 as runner

    missing = tmp_path / "missing.json"
    try:
        runner.registered_selection(missing)
    except ValueError as exc:
        assert "incomplete" in str(exc)
    else:
        raise AssertionError("missing calibration was accepted")

    reduced = tmp_path / "reduced.json"
    reduced.write_text(
        json.dumps(
            {
                "fully_registered_run": False,
                "decision": {"earliest_boundary_threshold": {"k": 32, "budget": 8192}},
            }
        )
    )
    try:
        runner.registered_selection(reduced)
    except ValueError as exc:
        assert "reduced" in str(exc)
    else:
        raise AssertionError("reduced calibration was accepted")


def test_v4_runner_uses_selected_budget_pair_and_quarter_migration(tmp_path: Path) -> None:
    from experiments.multi_island_hard import run_threshold_v4 as runner

    calibration = tmp_path / "calibration.json"
    calibration.write_text(
        json.dumps(
            {
                "fully_registered_run": True,
                "decision": {"earliest_boundary_threshold": {"k": 32, "budget": 8192}},
            }
        )
    )
    assert runner.registered_selection(calibration) == {"k": 32, "budget": 8192}

    runner.base.EXPECTED_REAL_ATTEMPTS = 8192
    command = runner.build_command(
        runner.TASKS["rugged512_k32_rep_v4"],
        "multi_island_4",
        tmp_path / "task" / "condition" / "rep-01",
    )
    assert "islands.migration.every=2048" in command
    assert "islands.migration.rank_window=2048" in command
    assert "run.stop.max_real_attempts_per_agent=1024" in command
    assert "grader.args.seed_index=0" in command
    assert "agents.count=8" in command
    for role_path in runner.POLICY_ROLES.values():
        protocol = role_path.read_text()
        assert ".coral_agent_id" in protocol
        assert "must never be hashed" in protocol
        assert "git show <commit>" not in protocol


def test_v4_canary_is_small_scripted_topology_matrix(tmp_path: Path) -> None:
    from experiments.multi_island_hard import run_threshold_v4_canary as canary

    canary.base.EXPECTED_REAL_ATTEMPTS = canary.CANARY_BUDGET
    command = canary.build_command(
        canary.TASKS[canary.CANARY_TASKS[0]],
        "multi_island_4",
        tmp_path / "task" / "condition" / "rep-01",
    )
    assert "agents.count=8" in command
    assert f"agents.runtime={canary.SCRIPTED_RUNTIME}" in command
    assert "agents.model=scripted" in command
    assert "agents.sandbox.network=allowlist" in command
    assert "agents.sandbox.allowed_domains=[]" in command
    assert any(item.startswith("agents.heartbeat=[") for item in command)
    assert any("scripted_search.py" in item for item in command)
    assert "run.stop.max_real_attempts=32" in command
    assert "run.stop.max_real_attempts_per_agent=4" in command
    assert "islands.count=4" in command
    assert "islands.migration.enabled=true" in command
    assert "islands.migration.every=8" in command
    assert "islands.migration.dest_weighting=round_robin" in command
    assert any('"--visible-agents","2"' in item for item in command)
    assert "agents.timeout=0" in command


def test_v4_canary_audit_rejects_duplicate_local_sequence() -> None:
    from experiments.multi_island_hard.audit_threshold_v4_canary import sequence_errors

    traces = [
        {
            "agent_id": f"agent-{agent}-from-atlantis",
            "local_attempt": local_attempt,
            "type": "initial" if local_attempt == 1 else "proposal",
        }
        for agent in range(8)
        for local_attempt in range(1, 5)
    ]
    assert sequence_errors(traces) == []
    traces[-1]["local_attempt"] = 1
    assert sequence_errors(traces) == [
        "agent-7: local attempts=[1, 1, 2, 3], expected [1, 2, 3, 4]"
    ]


def test_v4_scripted_runtime_entrypoint_and_mutation_kernel(
    monkeypatch, tmp_path: Path
) -> None:
    import runpy

    from coral.agent.registry import get_runtime
    from experiments.multi_island_hard.scripted_runtime import ScriptedRuntime

    assert isinstance(
        get_runtime("experiments.multi_island_hard.scripted_runtime:ScriptedRuntime"),
        ScriptedRuntime,
    )
    seed_dir = TASK_DIR / "seed_v4"
    monkeypatch.syspath_prepend(str(seed_dir))
    controller = runpy.run_path(str(seed_dir / "scripted_search.py"))
    first = controller["mutation_indices"]("captain-nemo", 1)
    assert first == controller["mutation_indices"]("captain-nemo-from-atlantis", 1)
    assert len(first) in {1, 2, 4}
    assert first != controller["mutation_indices"]("captain-nemo", 2)
    initial_a = controller["initial_title"]("captain-nemo-from-atlantis", 1)
    initial_b = controller["initial_title"]("sinbad-the-sailor-from-avalon", 1)
    assert initial_a != initial_b
    proposal_a = controller["proposal_title"]("captain-nemo-from-atlantis", 2, "a" * 40, 0.5, first)
    proposal_b = controller["proposal_title"]("sinbad-the-sailor-from-avalon", 2, "a" * 40, 0.5, first)
    assert proposal_a != proposal_b
    assert "attempt=2" in proposal_a

    checkout_globals = controller["checkout_visible"].__globals__
    checkout_globals["run"] = lambda command: ""
    checkout_globals["git_head"] = lambda root: "b" * 40
    assert controller["checkout_visible"](tmp_path, "a" * 40) is False
    checkout_globals["git_head"] = lambda root: "a" * 40
    assert controller["checkout_visible"](tmp_path, "a" * 40) is True

    root = tmp_path / "agent"
    root.mkdir()
    state = controller["load_state"](root, "captain-nemo-from-atlantis")
    assert state["completed_attempts"] == 0
    first_trace = {
        "type": "initial",
        "agent_id": "captain-nemo-from-atlantis",
        "local_attempt": 1,
        "candidate_sha256": "1" * 64,
    }
    state = controller["reserve_submission"](
        root,
        state,
        title="scripted initial attempt=1",
        trace=first_trace,
    )
    assert state["pending"]["local_attempt"] == 1
    state = controller["reconcile_pending"](
        root,
        "captain-nemo-from-atlantis",
        state,
        [
            {
                "agent_id": "captain-nemo-from-atlantis",
                "commit_hash": "a" * 40,
                "title": "scripted initial attempt=1",
                "status": "pending",
                "metadata": {"budget_class": "real"},
            }
        ],
    )
    assert state["completed_attempts"] == 1
    assert state["pending"] is None

    second_trace = {
        "type": "proposal",
        "agent_id": "captain-nemo-from-atlantis",
        "local_attempt": 2,
        "candidate_sha256": "2" * 64,
    }
    state = controller["reserve_submission"](
        root,
        state,
        title="scripted proposal attempt=2",
        trace=second_trace,
    )
    # The worktree-local journal survives a restart after the shared attempts
    # symlink is repointed to another island.
    reloaded = controller["load_state"](root, "captain-nemo-from-avalon")
    assert reloaded == state
    migrated_record = {
        "agent_id": "captain-nemo-from-atlantis",
        "commit_hash": "b" * 40,
        "title": "scripted proposal attempt=2",
        "status": "improved",
        "score": 0.75,
        "metadata": {"budget_class": "real", "island_id": "avalon"},
    }
    state = controller["reconcile_pending"](
        root,
        "captain-nemo-from-atlantis",
        reloaded,
        [migrated_record],
    )
    assert state["completed_attempts"] == 2
    assert state["pending"] is None
    # Reconciliation is idempotent and never emits a duplicate local attempt.
    assert controller["reconcile_pending"](
        root,
        "captain-nemo-from-atlantis",
        state,
        [migrated_record],
    ) == state
    traces = [
        json.loads(line)
        for line in controller["trace_path"](root).read_text().splitlines()
    ]
    assert [trace["local_attempt"] for trace in traces] == [1, 2]
    assert [trace["commit_hash"] for trace in traces] == ["a" * 40, "b" * 40]
    assert [trace["admission_recovery_submissions"] for trace in traces] == [0, 0]


def test_v4_scripted_policy_recovers_reserved_but_unadmitted_candidate(
    monkeypatch, tmp_path: Path
) -> None:
    import runpy

    seed_dir = TASK_DIR / "seed_v4"
    monkeypatch.syspath_prepend(str(seed_dir))
    controller = runpy.run_path(str(seed_dir / "scripted_search.py"))
    root = tmp_path / "agent"
    attempts_dir = tmp_path / "attempts"
    root.mkdir()
    attempts_dir.mkdir()
    candidate = "01" * 256
    controller["write_candidate"](root / "candidate.py", candidate)
    agent_id = "captain-nemo-from-atlantis"
    title = "scripted registered initial candidate attempt=1"
    trace = {
        "type": "initial",
        "agent_id": agent_id,
        "local_attempt": 1,
        "candidate_sha256": hashlib.sha256(candidate.encode()).hexdigest(),
    }
    state = controller["reserve_submission"](
        root,
        controller["initial_state"](agent_id),
        title=title,
        trace=trace,
    )

    calls: list[list[str]] = []

    def admit_recovery(command: list[str]) -> str:
        calls.append(command)
        assert controller["literal_candidate"](root / "candidate.py") == candidate
        assert "# Admission recovery nonce: 1" in (root / "candidate.py").read_text()
        record = {
            "agent_id": agent_id,
            "commit_hash": "c" * 40,
            "title": title,
            "status": "pending",
            "metadata": {"budget_class": "real"},
        }
        (attempts_dir / f"{record['commit_hash']}.json").write_text(json.dumps(record))
        return ""

    controller["recover_pending"].__globals__["run"] = admit_recovery
    controller["recover_pending"].__globals__["clear_stale_worktree_index_lock"] = (
        lambda root: False
    )
    recovered = controller["recover_pending"](
        root,
        agent_id,
        attempts_dir,
        state,
        visibility_timeout=0,
    )

    assert calls == [["coral", "eval", "--no-wait", "-m", title]]
    assert recovered["completed_attempts"] == 1
    assert recovered["pending"] is None
    traces = [
        json.loads(line)
        for line in controller["trace_path"](root).read_text().splitlines()
    ]
    assert len(traces) == 1
    assert traces[0]["local_attempt"] == 1
    assert traces[0]["candidate_sha256"] == trace["candidate_sha256"]
    assert traces[0]["admission_recovery_submissions"] == 1


def test_v4_scripted_submission_reconciles_record_instead_of_mutable_head(
    monkeypatch, tmp_path: Path
) -> None:
    import runpy

    seed_dir = TASK_DIR / "seed_v4"
    monkeypatch.syspath_prepend(str(seed_dir))
    controller = runpy.run_path(str(seed_dir / "scripted_search.py"))
    root = tmp_path / "agent"
    attempts_dir = tmp_path / "attempts"
    root.mkdir()
    attempts_dir.mkdir()
    agent_id = "captain-nemo"
    title = "scripted registered initial candidate attempt=1"
    commit_hash = "a" * 40

    def admit(_command: list[str]) -> str:
        record = {
            "agent_id": agent_id,
            "commit_hash": commit_hash,
            "title": title,
            "status": "pending",
            "metadata": {"budget_class": "real"},
        }
        (attempts_dir / f"{commit_hash}.json").write_text(json.dumps(record))
        return ""

    globals_ = controller["submit_reserved"].__globals__
    globals_["run"] = admit
    globals_["git_head"] = lambda _root: (_ for _ in ()).throw(
        AssertionError("post-eval HEAD must not identify the admitted attempt")
    )
    state = controller["submit_reserved"](
        root,
        agent_id,
        attempts_dir,
        controller["initial_state"](agent_id),
        title=title,
        trace={
            "type": "initial",
            "agent_id": agent_id,
            "local_attempt": 1,
            "candidate_sha256": "1" * 64,
        },
    )

    assert state["completed_attempts"] == 1
    assert state["last_commit_hash"] == commit_hash
    assert state["pending"] is None


def test_v4_scripted_policy_recovery_fails_closed_on_candidate_mismatch(
    monkeypatch, tmp_path: Path
) -> None:
    import runpy

    seed_dir = TASK_DIR / "seed_v4"
    monkeypatch.syspath_prepend(str(seed_dir))
    controller = runpy.run_path(str(seed_dir / "scripted_search.py"))
    root = tmp_path / "agent"
    attempts_dir = tmp_path / "attempts"
    root.mkdir()
    attempts_dir.mkdir()
    controller["write_candidate"](root / "candidate.py", "0" * 512)
    agent_id = "captain-nemo-from-atlantis"
    state = controller["reserve_submission"](
        root,
        controller["initial_state"](agent_id),
        title="scripted registered initial candidate attempt=1",
        trace={
            "type": "initial",
            "agent_id": agent_id,
            "local_attempt": 1,
            "candidate_sha256": hashlib.sha256(("1" * 512).encode()).hexdigest(),
        },
    )

    with pytest.raises(RuntimeError, match="candidate hash does not match"):
        controller["recover_pending"](
            root,
            agent_id,
            attempts_dir,
            state,
            visibility_timeout=0,
        )


def test_v4_auditor_recomputes_registered_mutation_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import runpy

    from experiments.multi_island_hard.audit_threshold_v4_canary import (
        expected_mutation_indices,
    )

    seed_dir = TASK_DIR / "seed_v4"
    monkeypatch.syspath_prepend(str(seed_dir))
    controller = runpy.run_path(str(seed_dir / "scripted_search.py"))
    for agent in ("captain-nemo", "captain-ahab-from-atlantis"):
        for local_attempt in (2, 3, 17, 128):
            assert expected_mutation_indices(agent, local_attempt) == controller[
                "mutation_indices"
            ](agent, local_attempt - 1)


def test_v4_scripted_policy_clears_only_its_stale_git_index_lock(
    monkeypatch, tmp_path: Path
) -> None:
    import runpy

    seed_dir = TASK_DIR / "seed_v4"
    monkeypatch.syspath_prepend(str(seed_dir))
    controller = runpy.run_path(str(seed_dir / "scripted_search.py"))
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    lock = root / ".git/index.lock"
    lock.write_text("orphan")

    assert controller["clear_stale_worktree_index_lock"](root) is True
    assert not lock.exists()
    assert controller["clear_stale_worktree_index_lock"](root) is False


def test_v4_scripted_leaderboard_tracks_current_island_visibility(
    monkeypatch, tmp_path: Path
) -> None:
    import runpy

    seed_dir = TASK_DIR / "seed_v4"
    monkeypatch.syspath_prepend(str(seed_dir))
    controller = runpy.run_path(str(seed_dir / "scripted_search.py"))
    attempts = tmp_path / "attempts"
    attempts.mkdir()

    def record(agent: str, commit: str, score: float) -> dict[str, object]:
        payload: dict[str, object] = {
            "agent_id": agent,
            "commit_hash": commit,
            "title": "scripted",
            "status": "improved",
            "score": score,
            "metadata": {"budget_class": "real"},
        }
        (attempts / f"{commit}.json").write_text(json.dumps(payload))
        return payload

    first = record("captain-nemo-from-atlantis", "a" * 40, 0.6)
    second = record("captain-ahab-from-atlantis", "b" * 40, 0.7)
    assert [
        row["commit_hash"]
        for row in controller["visible_leaders"](attempts, publish=first)
    ] == ["a" * 40]
    assert [
        row["commit_hash"]
        for row in controller["visible_leaders"](attempts, publish=second)
    ] == ["b" * 40, "a" * 40]

    # Migration moves Nemo's attempt file away; the next locked read removes
    # the stale entry, so a departed champion cannot leak across the boundary.
    (attempts / f"{'a' * 40}.json").unlink()
    assert [
        row["commit_hash"] for row in controller["visible_leaders"](attempts)
    ] == ["b" * 40]


def test_v4_isolation_preflight_and_trace_gate(tmp_path: Path) -> None:
    from experiments.multi_island.isolation_audit import (
        sandbox_contract_errors,
        trace_isolation_violations,
    )

    assert sandbox_contract_errors() == []

    run_dir = tmp_path / "run"
    own = run_dir / "agents" / "agent-a"
    foreign = run_dir / "agents" / "agent-b"
    own.mkdir(parents=True)
    foreign.mkdir(parents=True)
    (own / ".coral_island").write_text("avalon\n")
    (foreign / ".coral_island").write_text("atlantis\n")
    logs = run_dir / ".coral" / "islands" / "avalon" / "logs"
    (run_dir / ".coral" / "islands" / "atlantis" / "logs").mkdir(parents=True)
    logs.mkdir(parents=True)

    def event(tool: str, payload: dict[str, str]) -> str:
        return json.dumps(
            {
                "type": "tool_use",
                "part": {"tool": tool, "state": {"input": payload}},
            }
        )

    (logs / "agent-a.log").write_text(
        "\n".join(
            (
                event("bash", {"command": "git show coral/agent-b:candidate.py"}),
                event(
                    "write",
                    {
                        "filePath": str(
                            run_dir
                            / ".coral"
                            / "islands"
                            / "atlantis"
                            / "notes"
                            / "handoff.md"
                        )
                    },
                ),
                event("read", {"filePath": str(foreign / "candidate.py")}),
            )
        )
        + "\n"
    )
    violations = trace_isolation_violations(run_dir)
    assert any("raw-git-inspection" in item for item in violations)
    assert any("foreign-island-path:atlantis" in item for item in violations)
    assert any("foreign-agent-path:agent-b" in item for item in violations)


def test_v4_analyzer_requires_lineage_boundary_and_migration_effect() -> None:
    from experiments.multi_island_hard import analyze_threshold_v4 as analyzer

    budget = 8192
    rugged = "rugged512_k32_rep_v4"
    rows = [
        {
            "task": rugged,
            "budget": budget,
            "condition": "global_8",
            "final_inferred_lineages": 1,
        }
        for _ in range(8)
    ] + [
        {
            "task": rugged,
            "budget": budget,
            "condition": "multi_island_4",
            "final_inferred_lineages": 4,
        }
        for _ in range(8)
    ]
    contrasts = [
        {
            "task": rugged,
            "budget": budget,
            "contrast": "multi_island_4_minus_global_8",
            "paired_repetitions": 8,
            "confirmatory_ready": True,
            "random_z_difference": 0.5,
            "random_z_ci_low": 0.2,
            "mean_active_inferred_lineages_difference": 2.0,
            "mean_active_inferred_lineages_ci_low": 1.0,
        },
        {
            "task": rugged,
            "budget": budget,
            "contrast": "multi_island_4_minus_partition_4",
            "paired_repetitions": 8,
            "confirmatory_ready": True,
            "random_z_difference": 0.2,
            "random_z_ci_low": 0.05,
        },
        {
            "task": "rugged_minus_smooth",
            "budget": budget,
            "contrast": "difference_in_multi_minus_global",
            "paired_repetitions": 8,
            "confirmatory_ready": True,
            "random_z_difference": 0.4,
            "random_z_ci_low": 0.1,
        },
    ]
    result = analyzer.decision(
        rows,
        contrasts,
        policy="high_diffusion",
        budget=budget,
        rugged_task=rugged,
        repetitions=8,
    )
    assert result["boundary_threshold_supported"] is True
    assert result["migration_threshold_supported"] is True
    assert result["causal_policy_manipulation"] is True

    contrasts[1]["random_z_ci_low"] = -0.01
    result = analyzer.decision(
        rows,
        contrasts,
        policy="high_diffusion",
        budget=budget,
        rugged_task=rugged,
        repetitions=8,
    )
    assert result["boundary_threshold_supported"] is True
    assert result["migration_threshold_supported"] is False

    contrasts[1]["random_z_ci_low"] = 0.05
    contrasts[1]["confirmatory_ready"] = False
    contrasts[1]["paired_repetitions"] = 7
    result = analyzer.decision(
        rows,
        contrasts,
        policy="high_diffusion",
        budget=budget,
        rugged_task=rugged,
        repetitions=8,
    )
    assert result["confirmatory_ready"] is False
    assert result["boundary_threshold_supported"] is False
    assert result["migration_threshold_supported"] is False


def test_v4_analyzer_requires_attempt_after_last_migration(tmp_path: Path) -> None:
    from experiments.multi_island_hard.analyze_threshold_v4 import post_migration_attempt_gate

    public = tmp_path / ".coral/public"
    attempts = public / "attempts"
    attempts.mkdir(parents=True)
    (public / "migration_state.json").write_text(
        json.dumps({"schema_version": 1, "last_migrated_evals": {"agent-a": 1}})
    )
    for index, agent in enumerate(("agent-b", "agent-a"), start=1):
        (attempts / f"{index}.json").write_text(
            json.dumps(
                {
                    "commit_hash": str(index),
                    "agent_id": agent,
                    "status": "scored",
                    "score": 0.5,
                    "timestamp": f"2026-07-25T00:00:0{index}+00:00",
                    "metadata": {"budget_class": "real"},
                }
            )
        )
    assert post_migration_attempt_gate(tmp_path) == (True, [])
    (public / "migration_state.json").write_text(
        json.dumps({"schema_version": 1, "last_migrated_evals": {"agent-a": 2}})
    )
    assert post_migration_attempt_gate(tmp_path) == (False, ["agent-a"])


def test_v3_diagnostics_verify_unique_smooth_optimum_and_many_rugged_basins() -> None:
    data = json.loads((EXPERIMENT / "threshold_v3_diagnostics.json").read_text())
    smooth = [row for row in data["landscapes"] if row["task"] == "smooth256_rep_v3"]
    rugged = [row for row in data["landscapes"] if row["task"] == "rugged256_k32_rep_v3"]
    assert len(smooth) == len(rugged) == 8
    assert all(row["reference_is_exact"] and row["greedy_unique_maxima"] == 1 for row in smooth)
    assert all(
        not row["reference_is_exact"] and row["greedy_unique_maxima"] >= 60 for row in rugged
    )
    assert max(row["one_bit_autocorrelation"] for row in rugged) < min(
        row["one_bit_autocorrelation"] for row in smooth
    )


def test_v3_runner_uses_quarter_budget_and_separate_policy_roles(tmp_path: Path) -> None:
    from experiments.multi_island_hard import run_threshold_v3 as runner

    runner.base.EXPECTED_REAL_ATTEMPTS = 4096
    roles = {}
    for policy in runner.POLICY_ROLES:
        runner._ACTIVE_POLICY = policy
        command = runner.build_command(
            runner.base.TASKS["rugged256_k32_rep_v3"],
            "multi_island_4",
            tmp_path / "task" / "condition" / "rep-01",
        )
        assert "islands.migration.every=1024" in command
        assert "islands.migration.rank_window=1024" in command
        assert "run.stop.max_real_attempts_per_agent=512" in command
        assert "agents.timeout=240" in command
        roles[policy] = next(
            item for item in command if item.startswith("agents.runtime_options.role_file=")
        )
    assert roles["natural"] != roles["high_diffusion"]
    for role_path in runner.POLICY_ROLES.values():
        protocol = role_path.read_text()
        assert ".coral_agent_id" in protocol
        assert "must never be hashed" in protocol


def test_v3_analyzer_requires_behavior_manipulation_before_score_claim() -> None:
    from experiments.multi_island_hard import analyze_threshold_v3 as analyzer

    rows = [
        {
            "task": analyzer.RUGGED_TASK,
            "budget": 256,
            "condition": "global_8",
            "inferred_cross_agent_adoption_rate": 0.8,
        }
        for _ in range(8)
    ]
    contrasts = [
        {
            "task": analyzer.RUGGED_TASK,
            "budget": 256,
            "contrast": "multi_island_4_minus_global_8",
            "mean_active_inferred_lineages_difference": 2.0,
            "mean_active_inferred_lineages_ci_low": 1.0,
        },
        {
            "task": "rugged_minus_smooth",
            "budget": 256,
            "threshold_rule_passes": True,
        },
    ]
    positive = analyzer.mechanism_decision(rows, contrasts, policy="high_diffusion", repetitions=8)
    natural = analyzer.mechanism_decision(rows, contrasts, policy="natural", repetitions=8)
    assert positive["earliest_supported_multi_island_threshold"] == 256
    assert natural["earliest_supported_multi_island_threshold"] is None
    rows[0]["inferred_cross_agent_adoption_rate"] = 0.0
    rows[1]["inferred_cross_agent_adoption_rate"] = 0.0
    rows[2]["inferred_cross_agent_adoption_rate"] = 0.0
    rows[3]["inferred_cross_agent_adoption_rate"] = 0.0
    rows[4]["inferred_cross_agent_adoption_rate"] = 0.0
    failed = analyzer.mechanism_decision(rows, contrasts, policy="high_diffusion", repetitions=8)
    assert failed["earliest_supported_multi_island_threshold"] is None


def test_behavior_metrics_detect_strategy_collapse_and_foreign_parent() -> None:
    def record(agent: str) -> dict[str, str]:
        return {"agent_id": agent}

    parsed = [
        (record("a"), "00000000"),
        (record("b"), "11111111"),
        (record("a"), "00000001"),
        (record("b"), "00000000"),
        (record("a"), "00000011"),
    ]
    metrics = behavior_metrics(parsed)
    assert metrics["local_transition_rate"] == 1.0
    assert metrics["operator_entropy"] == 0.0
    assert metrics["inferred_cross_agent_adoptions"] == 1
    assert metrics["exact_foreign_copies"] == 1
    assert metrics["final_inferred_lineages"] == 1


def test_threshold_analyzer_accepts_only_unscored_rejected_tune(tmp_path: Path) -> None:
    from experiments.multi_island_hard import analyze_threshold_v2 as analyzer

    attempts = tmp_path / ".coral/public/attempts"
    attempts.mkdir(parents=True)

    def write(name: str, budget_class: str, score, feedback: str) -> None:
        (attempts / f"{name}.json").write_text(
            json.dumps(
                {
                    "commit_hash": name,
                    "status": "crashed" if score is None else "scored",
                    "score": score,
                    "feedback": feedback,
                    "metadata": {"budget_class": budget_class},
                }
            )
        )

    write(
        "rejected",
        "tune",
        None,
        f"prefix: {analyzer.TUNE_DISABLED_MARKER}; submit an ordinary eval",
    )
    assert analyzer.disallowed_records(tmp_path) == []

    write("scored-tune", "tune", 0.5, analyzer.TUNE_DISABLED_MARKER)
    write("grader-error", "grader_error", None, "worker crashed")
    assert {record["commit_hash"] for record in analyzer.disallowed_records(tmp_path)} == {
        "scored-tune",
        "grader-error",
    }


def test_threshold_analyzer_orders_retained_retry_directories(tmp_path: Path) -> None:
    from experiments.multi_island_hard import analyze_threshold_v2 as analyzer

    base = tmp_path / "rep-01"
    for path in (base.with_name("rep-01-retry-10"), base, base.with_name("rep-01-retry-02")):
        path.mkdir()
    assert [path.name for path in analyzer.existing_run_dirs(base)] == [
        "rep-01",
        "rep-01-retry-02",
        "rep-01-retry-10",
    ]
