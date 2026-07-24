"""Tests for the v7 oracle-free high-difficulty threshold package."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRADER_FILE = ROOT / "experiments/multi_island_modular/tasks/hard_active_modular_landscape_v7/grader/src/hard_active_modular_landscape_v7_grader/grader.py"
TASKDATA = ROOT / "experiments/multi_island_modular/tasks/hard_active_modular_landscape_v7/taskdata/hard_v7_seed_bundle.json"
SPEC = importlib.util.spec_from_file_location("hard_v7_grader_under_test", GRADER_FILE)
assert SPEC is not None and SPEC.loader is not None
GRADER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GRADER)


def candidate_source(modules: list[str], active: int = 0) -> str:
    literals = ",\n".join(f'    "{module}"' for module in modules)
    return f"CANDIDATE = (\n{literals}\n)\nACTIVE_MODULE = {active}\n"


def evaluate(tmp_path: Path, modules: list[str], *, mode: str, active: int = 0):
    from coral.config import GraderConfig
    from coral.types import Task

    private = tmp_path / f"private-{mode}-{sum(module != '0' * GRADER.WIDTH for module in modules)}"
    codebase = tmp_path / f"codebase-{mode}-{sum(module != '0' * GRADER.WIDTH for module in modules)}"
    private.mkdir()
    codebase.mkdir()
    shutil.copy(TASKDATA, private / "hard_v7_seed_bundle.json")
    (codebase / "candidate.py").write_text(candidate_source(modules, active))
    grader = GRADER.Grader(
        GraderConfig(
            args={
                "program_file": "candidate.py",
                "seed_bundle_file": "hard_v7_seed_bundle.json",
                "seed_index": 0,
                "mode": mode,
            }
        )
    )
    grader.private_dir = str(private)
    grader.codebase_path = str(codebase)
    grader.tasks = [Task(id="v7", name="v7", description="smoke")]
    return grader.evaluate()


def test_v7_dimensions_and_parser(tmp_path: Path) -> None:
    modules = ["0" * GRADER.WIDTH for _ in range(GRADER.BLOCKS)]
    path = tmp_path / "candidate.py"
    path.write_text(candidate_source(modules, active=47))
    candidate, active = GRADER.parse_candidate(path)
    assert len(candidate) == GRADER.TOTAL_WIDTH == 3072
    assert GRADER.BLOCKS == 48
    assert GRADER.WIDTH == 64
    assert active == 47


def test_v7_all_task_variants_parse() -> None:
    from coral.config import CoralConfig

    task_dir = ROOT / "experiments/multi_island_modular/tasks/hard_active_modular_landscape_v7"
    for name in ("task.yaml", "task_smooth_v7.yaml", "task_rugged_v7.yaml"):
        config = CoralConfig.from_yaml(task_dir / name)
        assert config.task.tips
        assert config.grader.direction == "maximize"


def test_v7_feedback_has_no_inactive_assembly_oracle(tmp_path: Path) -> None:
    seed = json.loads(TASKDATA.read_text())["seeds"][0]
    targets = GRADER.targets_for(seed, "smooth")
    zero = ["0" * GRADER.WIDTH for _ in range(GRADER.BLOCKS)]
    one_inactive_exact = zero.copy()
    one_inactive_exact[1] = targets[1]
    baseline = evaluate(tmp_path, zero, mode="smooth", active=0)
    carried = evaluate(tmp_path, one_inactive_exact, mode="smooth", active=0)
    assert baseline.aggregated == carried.aggregated
    explanation = carried.scores["eval"].explanation
    assert explanation is not None
    payload = json.loads(explanation)
    assert set(payload) == {"active_module", "active_score", "tested"}
    assert "artifact_exact_count" not in explanation


def test_v7_malformed_candidate_is_numeric_agent_penalty(tmp_path: Path) -> None:
    from coral.config import GraderConfig
    from coral.types import Task

    private = tmp_path / "private-invalid"
    codebase = tmp_path / "codebase-invalid"
    private.mkdir()
    codebase.mkdir()
    shutil.copy(TASKDATA, private / "hard_v7_seed_bundle.json")
    (codebase / "candidate.py").write_text(
        'CANDIDATE = tuple("0" * 64 for _ in range(48))\nACTIVE_MODULE = 0\n'
    )
    grader = GRADER.Grader(
        GraderConfig(
            args={
                "program_file": "candidate.py",
                "seed_bundle_file": "hard_v7_seed_bundle.json",
                "seed_index": 0,
                "mode": "smooth",
            }
        )
    )
    grader.private_dir = str(private)
    grader.codebase_path = str(codebase)
    grader.tasks = [Task(id="v7", name="v7", description="invalid candidate")]
    result = grader.evaluate()
    assert result.aggregated == 0.0
    explanation = result.scores["eval"].explanation
    assert explanation is not None
    assert json.loads(explanation)["tested"] is False
    assert "invalid_candidate" in explanation


def test_v7_smooth_anchor_and_rugged_codebook() -> None:
    assert GRADER.BLOCKS * (GRADER.WIDTH + 2) == 3168
    assert len(GRADER.CODEBOOK) == 4096
    assert "0" * GRADER.WIDTH not in GRADER.CODEBOOK
    bundle = json.loads(TASKDATA.read_text())
    assert bundle["schema_version"] == 5
    for seed in bundle["seeds"]:
        targets = [GRADER.rugged_target(seed, block) for block in range(GRADER.BLOCKS)]
        assert len(set(targets)) == GRADER.BLOCKS


def test_v7_rugged_exact_beats_nonzero_and_decoy() -> None:
    target = "1" * GRADER.WIDTH
    assert GRADER.active_score("0" * GRADER.WIDTH, mode="rugged", target=target) == 0.08
    assert (
        GRADER.active_score("1" * GRADER.WIDTH, mode="rugged", target="0" * GRADER.WIDTH)
        == 0.10
    )
    assert GRADER.active_score(target, mode="rugged", target=target) == 1.0


def test_v7_calibration_is_materially_harder_than_v6() -> None:
    calibration = json.loads(
        (ROOT / "experiments/multi_island_modular/hard_v7_calibration.json").read_text()
    )
    smooth, rugged = calibration["tasks"]
    assert smooth["cost_mean"] == 3168
    assert rugged["cost_min"] > 80_000
    assert rugged["cost_mean"] > 100_000
    assert calibration["feedback"] == "active_module_only"


def test_v7_runner_records_fixed_protocol(tmp_path: Path) -> None:
    from experiments.multi_island_modular import analyze_hard_v7 as analyzer
    from experiments.multi_island_modular import run_hard_v7 as runner

    assert runner.HEARTBEAT_OVERRIDE == analyzer.HEARTBEAT_OVERRIDE
    assert runner.migration_every(1024) == 256
    assert runner.migration_every(8192) == 2048
    assert runner.migration_every(196608) == 2048
    runner.base.EXPECTED_REAL_ATTEMPTS = 3072
    command = runner.build_command(
        runner.base.TASKS["smooth_hard_v7"],
        "global_8",
        tmp_path / "rep-01",
    )
    heartbeat = next(item for item in command if item.startswith("agents.heartbeat="))
    assert heartbeat == f"agents.heartbeat={runner.HEARTBEAT_OVERRIDE}"
    assert "agents.count=8" in command
    assert "run.stop.max_real_attempts_per_agent=384" in command
    assert "grader.args.seed_index=0" in command


def test_v7_agent_balance_gate(monkeypatch, tmp_path: Path) -> None:
    from experiments.multi_island_modular import analyze_hard_v7 as analyzer

    records = [
        {"agent_id": f"agent-{agent}"}
        for agent in range(8)
        for _ in range(8)
    ]
    monkeypatch.setattr(analyzer.base, "real_records", lambda _run_dir: records)
    balanced = analyzer._agent_balance(tmp_path, 64)
    assert balanced["agent_quota_gate"] is True
    records.extend({"agent_id": "agent-0"} for _ in range(8))
    imbalanced = analyzer._agent_balance(tmp_path, 72)
    assert imbalanced["agent_quota_gate"] is False


def test_v7_analyzer_uses_preregistered_default_budgets(monkeypatch) -> None:
    import sys

    from experiments.multi_island_modular import analyze_hard_v7 as analyzer

    monkeypatch.setattr(sys, "argv", ["analyze_hard_v7.py"])
    args = analyzer.base.parse_args()
    assert args.budgets == list(analyzer.base.DEFAULT_BUDGETS)
    assert args.budgets[:6] == [1024, 2048, 3072, 4096, 6144, 8192]
    assert args.budgets[-1] == 196608
    assert analyzer.base.MAX_MALFORMED_ATTEMPTS == 1


def test_v7_duplicate_query_diagnostics(monkeypatch, tmp_path: Path) -> None:
    from experiments.multi_island_modular import analyze_hard_v7 as analyzer

    zero = "0" * analyzer.WIDTH
    source = candidate_source([zero] * analyzer.BLOCKS, active=0)
    records = [
        {
            "commit_hash": "first",
            "agent_id": "agent-a",
            "score": 0.5,
            "timestamp": "1",
            "metadata": {"budget_class": "real"},
            "_attempt_path": str(
                tmp_path / "islands" / "atlantis" / "attempts" / "first.json"
            ),
        },
        {
            "commit_hash": "same-island",
            "agent_id": "agent-b",
            "score": 0.5,
            "timestamp": "2",
            "metadata": {"budget_class": "real"},
            "_attempt_path": str(
                tmp_path / "islands" / "atlantis" / "attempts" / "same.json"
            ),
        },
        {
            "commit_hash": "other-island",
            "agent_id": "agent-c",
            "score": 0.5,
            "timestamp": "3",
            "metadata": {"budget_class": "real"},
            "_attempt_path": str(
                tmp_path / "islands" / "avalon" / "attempts" / "other.json"
            ),
        },
    ]
    monkeypatch.setattr(analyzer.base, "real_records", lambda _run_dir: records)
    monkeypatch.setattr(analyzer.base, "source_at", lambda _run_dir, _commit: source)
    row = analyzer._BASE_COLLECT(
        tmp_path,
        {"condition": "multi_island", "repetition": 1},
        "smooth_hard_v7",
        budget=3,
    )
    assert row["unique_queries"] == 1
    assert row["duplicate_queries"] == 2
    assert row["duplicate_query_rate"] == 2 / 3
    assert row["cross_island_duplicate_queries"] == 1
