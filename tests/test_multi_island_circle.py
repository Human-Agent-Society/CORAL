"""Tests for the real-artifact Circle Packing topology study."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRADER_FILE = ROOT / "examples/math/circle_packing/grader/src/circle_packing_grader/grader.py"
SPEC = importlib.util.spec_from_file_location("circle_packing_grader_under_test", GRADER_FILE)
assert SPEC is not None and SPEC.loader is not None
GRADER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GRADER)


def test_circle_packing_control_rejects_tune_before_scoring() -> None:
    from coral.config import GraderConfig
    from coral.types import Task

    grader = GRADER.Grader(GraderConfig(args={"disable_tune": True}))
    grader.tasks = [
        Task(
            id="circle",
            name="circle",
            description="test",
            metadata={"budget_class": "tune"},
        )
    ]
    result = grader.evaluate()
    assert result.aggregated is None
    assert "Tune mode is disabled for this controlled experiment" in str(
        result.scores["eval"].explanation
    )


def test_circle_packing_hardened_namespace_hides_host_paths() -> None:
    script = (
        "import os, socket\n"
        "print(os.path.exists('/work/initial_program.py'))\n"
        "print(os.path.exists('/var/tmp/coral-institutions-results'))\n"
        f"print(os.path.exists({str(ROOT / 'blog/agents-need-institutions.html')!r}))\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=0.1)\n"
        "    print(True)\n"
        "except OSError:\n"
        "    print(False)\n"
    )
    command = GRADER._sandboxed_command(
        ROOT / "examples/math/circle_packing/seed",
        script,
        [],
    )
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["True", "False", "False", "False"]


def test_circle_runner_freezes_budget_topology_and_candidate_timeout(tmp_path: Path) -> None:
    from experiments.multi_island_circle import run_circle as runner

    runner.base.EXPECTED_REAL_ATTEMPTS = 64
    command = runner.build_command(
        runner.base.TASKS[runner.TASK_NAME],
        "multi_island",
        tmp_path / "circle_packing" / "multi_island" / "rep-01",
    )
    expected = {
        "agents.count=4",
        "agents.timeout=900",
        "agents.sandbox.network=allowlist",
        'agents.sandbox.allowed_domains=["api.appintheloop.com"]',
        "grader.timeout=660",
        "grader.args.evaluation_timeout=600",
        "grader.args.harden_candidate=true",
        "grader.args.disable_tune=true",
        "grader.parallel.max_workers=2",
        "islands.count=2",
        "islands.migration.enabled=true",
        "islands.migration.every=16",
        "islands.migration.rank_window=16",
        "islands.migration.remigration_cooldown=16",
        "run.stop.max_real_attempts=64",
        "run.stop.max_real_attempts_per_agent=16",
    }
    assert expected.issubset(command)


def test_circle_runner_rotates_sequential_condition_order() -> None:
    from experiments.multi_island_circle import run_circle as runner

    cells = list(
        runner.latin_square_cells([runner.TASK_NAME], list(runner.CONDITIONS), 3)
    )
    orders = [
        [condition for _spec, condition, repetition in cells if repetition == block]
        for block in (1, 2, 3)
    ]
    assert orders == [
        ["global", "partition", "multi_island"],
        ["partition", "multi_island", "global"],
        ["multi_island", "global", "partition"],
    ]


def test_circle_source_audit_blocks_external_or_private_lookup() -> None:
    from experiments.multi_island_circle.analyze_circle import forbidden_candidate_io

    assert forbidden_candidate_io("import numpy as np\nfrom scipy.optimize import minimize\n") == []
    assert forbidden_candidate_io("import requests\nrequests.get('https://example.com')\n")
    assert forbidden_candidate_io("open('/var/tmp/coral-institutions-results/prior')\n")
    assert forbidden_candidate_io("open('.coral/private/answer.json')\n")


def test_circle_threshold_requires_both_partition_and_global_contrasts() -> None:
    from experiments.multi_island_circle import analyze_circle as analyzer

    rows = []
    for repetition in range(1, 9):
        for condition, score in (
            ("global", 0.70),
            ("partition", 0.71),
            ("multi_island", 0.73),
        ):
            rows.append(
                {
                    "budget": 32,
                    "condition": condition,
                    "repetition": repetition,
                    "final_best_score": score,
                    "gain_over_seed": score - analyzer.SEED_SCORE,
                    "best_so_far_auc": score - 0.01,
                    "latest_source_diversity": 0.5,
                    "null_rate": 0.0,
                    "migration_notes": 2 if condition == "multi_island" else 0,
                    "post_migration_attempts": 4 if condition == "multi_island" else 0,
                }
            )
    contrasts, threshold = analyzer.make_contrasts(rows, 8)
    assert threshold["earliest_supported_multi_island_threshold"] == 32
    primary = next(
        row for row in contrasts if row["contrast"] == "multi_island_minus_partition"
    )
    secondary = next(
        row for row in contrasts if row["contrast"] == "multi_island_minus_global"
    )
    assert primary["contrast_rule_passes"] is True
    assert secondary["contrast_rule_passes"] is True
