"""Tests for the replicated N=128 Smooth/Rugged threshold v2 study."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = ROOT / "experiments/multi_island_hard/tasks/institutional_landscape"
GRADER_FILE = TASK_DIR / "grader/src/institutional_landscape_grader/grader.py"
SPEC = importlib.util.spec_from_file_location("institutional_v2_grader_under_test", GRADER_FILE)
assert SPEC is not None and SPEC.loader is not None
GRADER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GRADER)


def evaluate(tmp_path: Path, landscape: str, candidate: str, *, seed_index: int = 0):
    from coral.config import GraderConfig
    from coral.types import Task

    private = tmp_path / f"private-{landscape}-{seed_index}"
    codebase = tmp_path / f"codebase-{landscape}-{seed_index}"
    private.mkdir()
    codebase.mkdir()
    shutil.copy(TASK_DIR / "taskdata" / landscape, private / landscape)
    (codebase / "candidate.py").write_text(f"CANDIDATE = {candidate!r}\n")
    grader = GRADER.Grader(
        GraderConfig(
            args={
                "program_file": "candidate.py",
                "landscape_file": landscape,
                "seed_index": seed_index,
            }
        )
    )
    grader.private_dir = str(private)
    grader.codebase_path = str(codebase)
    grader.tasks = [Task(id="nk-v2", name="nk-v2", description="smoke")]
    return grader.evaluate()


def test_replicated_landscape_schema_preserves_legacy_and_rotates_seed() -> None:
    legacy = GRADER.load_landscape(TASK_DIR / "taskdata/smooth128.json", 0)
    replicated0 = GRADER.load_landscape(
        TASK_DIR / "taskdata/smooth128_replicated_v2.json", 0
    )
    replicated1 = GRADER.load_landscape(
        TASK_DIR / "taskdata/smooth128_replicated_v2.json", 1
    )
    assert legacy[:2] == replicated0[:2] == replicated1[:2] == (128, 0)
    assert legacy[3] is False
    assert replicated0[3] is replicated1[3] is True
    assert replicated0[2] != replicated1[2]


def test_replicated_grader_charges_malformed_candidate_as_numeric_zero(tmp_path: Path) -> None:
    result = evaluate(
        tmp_path,
        "smooth128_replicated_v2.json",
        "not-128-bits",
    )
    assert result.aggregated == 0.0
    explanation = result.scores["eval"].explanation
    assert explanation is not None and "Invalid candidate:" in explanation


def test_replicated_variants_parse_and_network_is_closed() -> None:
    from coral.config import CoralConfig

    for name in (
        "task_smooth128_replicated_v2.yaml",
        "task_rugged128_k12_replicated_v2.yaml",
    ):
        config = CoralConfig.from_yaml(TASK_DIR / name)
        assert config.agents.count == 8
        assert config.agents.sandbox.network == "allowlist"
        assert config.agents.sandbox.allowed_domains == []
        assert config.grader.args["seed_index"] == 0


def test_threshold_v2_diagnostics_separate_smooth_and_rugged() -> None:
    data = json.loads(
        (ROOT / "experiments/multi_island_hard/threshold_v2_diagnostics.json").read_text()
    )
    smooth = [row for row in data["landscapes"] if row["task"] == "smooth128_rep_v2"]
    rugged = [
        row for row in data["landscapes"] if row["task"] == "rugged128_k12_rep_v2"
    ]
    assert len(smooth) == len(rugged) == 8
    assert all(row["reference_is_exact"] and row["greedy_unique_maxima"] == 1 for row in smooth)
    assert all(not row["reference_is_exact"] and row["greedy_unique_maxima"] > 20 for row in rugged)
    assert max(row["one_bit_autocorrelation"] for row in rugged) < min(
        row["one_bit_autocorrelation"] for row in smooth
    )


def test_threshold_v2_initial_candidates_are_topology_invariant_and_distinct() -> None:
    from experiments.multi_island_hard import analyze_threshold_v2 as analyzer

    names = (
        "captain-nemo",
        "captain-ahab",
        "jack-sparrow",
        "davy-jones",
        "long-john-silver",
        "sinbad-the-sailor",
        "horatio-hornblower",
        "jack-aubrey",
    )
    candidates = {analyzer.initial_candidate(name) for name in names}
    assert len(candidates) == 8
    assert all(len(candidate) == 128 and not set(candidate) - {"0", "1"} for candidate in candidates)
    assert analyzer.initial_candidate("captain-nemo") == analyzer.initial_candidate(
        "captain-nemo-from-atlantis"
    )


def test_threshold_v2_runner_records_registered_protocol(tmp_path: Path) -> None:
    from experiments.multi_island_hard import run_threshold_v2 as runner

    runner.base.EXPECTED_REAL_ATTEMPTS = 512
    command = runner.build_command(
        runner.base.TASKS["rugged128_k12_rep_v2"],
        "multi_island_4",
        tmp_path / "rep-01",
    )
    assert "agents.count=8" in command
    assert "agents.sandbox.network=allowlist" in command
    assert "grader.parallel.max_workers=4" in command
    assert "islands.migration.every=128" in command
    assert "islands.migration.dest_weighting=round_robin" in command
    assert "islands.migration.max_per_cycle=4" in command
    assert "run.stop.max_real_attempts_per_agent=64" in command
    assert "grader.args.seed_index=0" in command


def test_threshold_v2_decision_rule_is_paired_and_ruggedness_specific() -> None:
    from experiments.multi_island_hard import analyze_threshold_v2 as analyzer

    rows = []
    for task in analyzer.TASKS:
        for repetition in range(1, 9):
            for condition in analyzer.CONDITIONS:
                effect = 0.0
                if task == analyzer.RUGGED_TASK:
                    effect = {
                        "global_8": 0.0,
                        "partition_4": 0.20,
                        "multi_island_2": 0.30,
                        "multi_island_4": 0.80,
                    }[condition]
                rows.append(
                    {
                        "task": task,
                        "budget": 128,
                        "condition": condition,
                        "repetition": repetition,
                        "random_z": 0.4 + effect,
                        "reference_gain": 0.4 + effect,
                        "best_so_far_auc_reference": 0.3 + effect,
                        "midpoint_diversity": 0.2 + effect,
                        "final_diversity": 0.1 + effect,
                        "duplicate_candidate_rate": 0.3 - effect / 10,
                    }
                )
    contrasts, threshold = analyzer.make_contrasts(rows, repetitions=8)
    interaction = next(
        row
        for row in contrasts
        if row["task"] == "rugged_minus_smooth" and row["budget"] == 128
    )
    assert interaction["paired_repetitions"] == 8
    assert abs(interaction["random_z_difference"] - 0.8) < 1e-12
    assert interaction["threshold_rule_passes"] is True
    assert threshold["earliest_full_multi_island_threshold"] == 128


def test_threshold_v2_calibration_and_confirmation_seeds_are_disjoint() -> None:
    root = ROOT / "experiments/multi_island_hard"
    calibration = json.loads((root / "threshold_v2_calibration_landscapes.json").read_text())
    smooth = json.loads((TASK_DIR / "taskdata/smooth128_replicated_v2.json").read_text())
    rugged = json.loads((TASK_DIR / "taskdata/rugged128_k12_replicated_v2.json").read_text())
    assert smooth["seeds"] == rugged["seeds"]
    assert set(calibration["seeds"]).isdisjoint(smooth["seeds"])


def test_threshold_v2_takeover_calibrator_supports_four_islands() -> None:
    from experiments.multi_island_hard import calibrate_threshold_v2_takeover as calibration

    groups = calibration.groups_for(4)
    assert groups == ((0, 4), (1, 5), (2, 6), (3, 7))
    assert {index for group in groups for index in group} == set(range(8))


def test_threshold_v2_calibrations_bound_the_claim_and_select_k12() -> None:
    root = ROOT / "experiments/multi_island_hard"
    conventional = json.loads((root / "threshold_v2_topology_calibration.json").read_text())
    takeover = json.loads((root / "threshold_v2_takeover_calibration.json").read_text())
    assert conventional["decision"]["calibration_supports_llm_threshold_study"] is False
    assert takeover["decision"]["calibration_supports_takeover_mechanism_study"] is True
    assert takeover["decision"]["selected_rugged_k"] == 12
    assert takeover["decision"]["selected_threshold_anchor_budget"] == 2048
