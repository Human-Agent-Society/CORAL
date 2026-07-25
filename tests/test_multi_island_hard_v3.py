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
        runner.base.TASKS["rugged512_k32_rep_v4"],
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
