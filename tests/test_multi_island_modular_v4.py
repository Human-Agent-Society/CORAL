"""Tests for the independent v4 hard modular package."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRADER_FILE = ROOT / "experiments/multi_island_modular/tasks/hard_active_modular_landscape_v4/grader/src/hard_active_modular_landscape_grader/grader.py"
TASKDATA = ROOT / "experiments/multi_island_modular/tasks/hard_active_modular_landscape_v4/taskdata/hard_v4_seed_bundle.json"
SPEC = importlib.util.spec_from_file_location("hard_v4_grader_under_test", GRADER_FILE)
assert SPEC is not None and SPEC.loader is not None
GRADER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GRADER)


def candidate_source(modules: list[str], active: int = 0) -> str:
    literals = ",\n".join(f'    "{module}"' for module in modules)
    return f"CANDIDATE = (\n{literals}\n)\nACTIVE_MODULE = {active}\n"


def test_tuple_candidate_and_legacy_string_parse(tmp_path: Path) -> None:
    modules = ["0" * GRADER.WIDTH for _ in range(GRADER.BLOCKS)]
    path = tmp_path / "candidate.py"
    path.write_text(candidate_source(modules, active=7))
    candidate, active = GRADER.parse_candidate(path)
    assert candidate == "".join(modules)
    assert active == 7

    path.write_text(f'CANDIDATE = "{"0" * GRADER.TOTAL_WIDTH}"\nACTIVE_MODULE = 3\n')
    candidate, active = GRADER.parse_candidate(path)
    assert len(candidate) == GRADER.TOTAL_WIDTH
    assert active == 3


def test_rugged_targets_are_unique_per_seed() -> None:
    bundle = json.loads(TASKDATA.read_text())
    for seed in bundle["seeds"]:
        targets = [GRADER.rugged_target(seed, block) for block in range(GRADER.BLOCKS)]
        assert len(set(targets)) == GRADER.BLOCKS


def test_rugged_trap_and_exact_scores() -> None:
    seed = json.loads(TASKDATA.read_text())["seeds"][0]
    target = GRADER.rugged_target(seed, 0)
    assert GRADER.active_score("0" * GRADER.WIDTH, mode="rugged", target=target) == 0.78
    assert GRADER.active_score(target, mode="rugged", target=target) == 1.0
    assert GRADER.active_score("1" * GRADER.WIDTH, mode="rugged", target=target) == 0.43
