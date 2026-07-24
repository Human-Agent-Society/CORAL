"""Tests for the v6 verified-assembly threshold package."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRADER_FILE = ROOT / "experiments/multi_island_modular/tasks/hard_active_modular_landscape_v6/grader/src/hard_active_modular_landscape_v6_grader/grader.py"
TASKDATA = ROOT / "experiments/multi_island_modular/tasks/hard_active_modular_landscape_v6/taskdata/hard_v6_seed_bundle.json"
SPEC = importlib.util.spec_from_file_location("hard_v6_grader_under_test", GRADER_FILE)
assert SPEC is not None and SPEC.loader is not None
GRADER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GRADER)


def candidate_source(modules: list[str], active: int = 0) -> str:
    literals = ",\n".join(f'    "{module}"' for module in modules)
    return f"CANDIDATE = (\n{literals}\n)\nACTIVE_MODULE = {active}\n"


def test_v6_dimensions_and_parser(tmp_path: Path) -> None:
    modules = ["0" * GRADER.WIDTH for _ in range(GRADER.BLOCKS)]
    path = tmp_path / "candidate.py"
    path.write_text(candidate_source(modules, active=47))
    candidate, active = GRADER.parse_candidate(path)
    assert len(candidate) == GRADER.TOTAL_WIDTH == 1536
    assert active == 47


def test_v6_assembly_reward_is_observable_and_exact_only() -> None:
    seed = json.loads(TASKDATA.read_text())["seeds"][0]
    targets = GRADER.targets_for(seed, "smooth")
    zero = "0" * GRADER.TOTAL_WIDTH
    one_exact = zero[: GRADER.WIDTH] + targets[1] + zero[2 * GRADER.WIDTH :]
    zero_score = GRADER.combined_score(zero, active=0, mode="smooth", seed=seed)
    assembled_score = GRADER.combined_score(one_exact, active=0, mode="smooth", seed=seed)
    assert zero_score[2] == 0
    assert assembled_score[2] == 1
    assert assembled_score[0] > zero_score[0]


def test_v6_smooth_anchor_and_rugged_codebook() -> None:
    assert GRADER.BLOCKS * (GRADER.WIDTH + 2) == 1632
    assert len(GRADER.CODEBOOK) == 2048
    assert "0" * GRADER.WIDTH not in GRADER.CODEBOOK
    bundle = json.loads(TASKDATA.read_text())
    assert bundle["schema_version"] == 4
    for seed in bundle["seeds"]:
        targets = [GRADER.rugged_target(seed, block) for block in range(GRADER.BLOCKS)]
        assert len(set(targets)) == GRADER.BLOCKS


def test_v6_rugged_exact_beats_nonzero_and_decoy() -> None:
    target = "1" * GRADER.WIDTH
    assert GRADER.active_score("0" * GRADER.WIDTH, mode="rugged", target=target) == 0.08
    assert GRADER.active_score("1" * GRADER.WIDTH, mode="rugged", target="0" * GRADER.WIDTH) == 0.10
    assert GRADER.active_score(target, mode="rugged", target=target) == 1.0


def test_v6_grader_loads_private_bundle_in_both_modes(tmp_path: Path) -> None:
    from coral.config import GraderConfig
    from coral.types import Task

    private = tmp_path / "private"
    codebase = tmp_path / "codebase"
    private.mkdir()
    codebase.mkdir()
    shutil.copy(TASKDATA, private / "hard_v6_seed_bundle.json")
    shutil.copy(
        ROOT / "experiments/multi_island_modular/tasks/hard_active_modular_landscape_v6/seed/candidate.py",
        codebase / "candidate.py",
    )
    for mode in ("smooth", "rugged"):
        grader = GRADER.Grader(
            GraderConfig(
                args={
                    "program_file": "candidate.py",
                    "seed_bundle_file": "hard_v6_seed_bundle.json",
                    "seed_index": 0,
                    "mode": mode,
                }
            )
        )
        grader.private_dir = str(private)
        grader.codebase_path = str(codebase)
        grader.tasks = [Task(id="v6", name="v6", description="smoke")]
        result = grader.evaluate()
        assert result.aggregated is not None
        assert result.aggregated > 0.0


def test_v6_migration_cadence_is_budget_scaled() -> None:
    from experiments.multi_island_modular.run_hard_v6 import migration_every

    assert migration_every(512) == 128
    assert migration_every(2048) == 512
    assert migration_every(65536) == 512


def test_v6_transfer_metric_uses_origin_and_destination(monkeypatch, tmp_path: Path) -> None:
    import sys

    sys.modules.pop("hard_active_modular_landscape_grader", None)
    sys.modules.pop("hard_active_modular_landscape_grader.grader", None)
    from experiments.multi_island_modular import analyze_hard_v6 as analyzer

    seed = json.loads(TASKDATA.read_text())["seeds"][0]
    target = GRADER.target_bits(seed, 0)
    zero = "0" * GRADER.WIDTH

    def source(modules: list[str], active: int) -> str:
        return candidate_source(modules, active)

    source_map = {
        "discover": source([target] + [zero] * (GRADER.BLOCKS - 1), 0),
        "reuse": source([target] + [zero] * (GRADER.BLOCKS - 1), 1),
    }
    records = [
        {
            "commit_hash": "discover",
            "score": 1.0,
            "timestamp": "1",
            "metadata": {"budget_class": "real", "origin_island_id": "atlantis"},
            "_attempt_path": str(tmp_path / "islands" / "atlantis" / "attempts" / "discover.json"),
        },
        {
            "commit_hash": "reuse",
            "score": 0.2,
            "timestamp": "2",
            "metadata": {"budget_class": "real", "origin_island_id": "avalon"},
            "_attempt_path": str(tmp_path / "islands" / "avalon" / "attempts" / "reuse.json"),
        },
    ]
    monkeypatch.setattr(analyzer.base, "real_records", lambda _run_dir: records)
    monkeypatch.setattr(analyzer.base, "source_at", lambda _run_dir, commit: source_map[commit])
    result = analyzer._observed_transfer(tmp_path, "smooth_hard_v6", 1)
    assert result["transfer_events"] == 1
    assert result["transferred_blocks"] == 1
