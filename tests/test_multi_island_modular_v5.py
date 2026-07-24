"""Tests for the independent v5 high-dimensional modular package."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRADER_FILE = ROOT / "experiments/multi_island_modular/tasks/hard_active_modular_landscape_v5/grader/src/hard_active_modular_landscape_v5_grader/grader.py"
TASKDATA = ROOT / "experiments/multi_island_modular/tasks/hard_active_modular_landscape_v5/taskdata/hard_v5_seed_bundle.json"
SPEC = importlib.util.spec_from_file_location("hard_v5_grader_under_test", GRADER_FILE)
assert SPEC is not None and SPEC.loader is not None
GRADER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GRADER)


def candidate_source(modules: list[str], active: int = 0) -> str:
    literals = ",\n".join(f'    "{module}"' for module in modules)
    return f"CANDIDATE = (\n{literals}\n)\nACTIVE_MODULE = {active}\n"


def test_v5_dimensions_and_tuple_parser(tmp_path: Path) -> None:
    modules = ["0" * GRADER.WIDTH for _ in range(GRADER.BLOCKS)]
    path = tmp_path / "candidate.py"
    path.write_text(candidate_source(modules, active=31))
    candidate, active = GRADER.parse_candidate(path)
    assert len(candidate) == GRADER.TOTAL_WIDTH == 1024
    assert active == 31


def test_v5_smooth_provenance_anchor() -> None:
    assert GRADER.BLOCKS * (GRADER.WIDTH + 2) == 1088
    assert GRADER.active_score("0" * GRADER.WIDTH, mode="smooth", target="1" * GRADER.WIDTH) == 0.05


def test_v5_rugged_codebook_and_unique_targets() -> None:
    bundle = json.loads(TASKDATA.read_text())
    assert bundle["schema_version"] == 3
    assert len(GRADER.CODEBOOK) == 1024
    assert "0" * GRADER.WIDTH not in GRADER.CODEBOOK
    for seed in bundle["seeds"]:
        targets = [GRADER.rugged_target(seed, block) for block in range(GRADER.BLOCKS)]
        assert len(set(targets)) == GRADER.BLOCKS


def test_v5_rugged_decoy_does_not_beat_exploration() -> None:
    target = "1" * GRADER.WIDTH
    decoy = GRADER.active_score("0" * GRADER.WIDTH, mode="rugged", target=target)
    wrong = GRADER.active_score("1" * GRADER.WIDTH, mode="rugged", target="0" * GRADER.WIDTH)
    exact = GRADER.active_score("0" * GRADER.WIDTH, mode="rugged", target="0" * GRADER.WIDTH)
    assert decoy == 0.38
    assert wrong == 0.42
    assert exact == 1.0
    assert decoy < wrong < exact
