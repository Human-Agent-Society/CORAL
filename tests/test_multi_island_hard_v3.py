"""Tests for the N=256 social-learning phase study."""

from __future__ import annotations

import json
from pathlib import Path

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
