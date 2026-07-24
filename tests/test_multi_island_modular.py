"""Calibration and grader checks for the modular multi-island follow-up."""

from __future__ import annotations

# The grader modules live in task-local source trees that are inserted below.
# noqa: E402 is intentionally scoped to this test module.
# ruff: noqa: E402
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GRADER_SRC = ROOT / "experiments/multi_island_modular/tasks/modular_landscape/grader/src"
sys.path.insert(0, str(GRADER_SRC))
ACTIVE_GRADER_SRC = (
    ROOT / "experiments/multi_island_modular/tasks/active_modular_landscape/grader/src"
)
HARD_GRADER_SRC = (
    ROOT / "experiments/multi_island_modular/tasks/hard_active_modular_landscape/grader/src"
)
sys.path.insert(0, str(ACTIVE_GRADER_SRC))
sys.path.insert(0, str(HARD_GRADER_SRC))

from active_modular_landscape_grader.grader import (  # noqa: E402
    CODEBOOK,
    active_score,
    rugged_target,
)
from hard_active_modular_landscape_grader.grader import (  # noqa: E402
    BLOCKS as HARD_BLOCKS,
)
from hard_active_modular_landscape_grader.grader import (
    CODEBOOK as HARD_CODEBOOK,
)
from hard_active_modular_landscape_grader.grader import (
    WIDTH as HARD_WIDTH,
)
from hard_active_modular_landscape_grader.grader import (
    active_score as hard_active_score,
)
from hard_active_modular_landscape_grader.grader import (
    rugged_target as hard_rugged_target,
)
from hard_active_modular_landscape_grader.grader import (
    target_bits as hard_target_bits,
)
from modular_landscape_grader.grader import evaluate_candidate, target_bits  # noqa: E402

from experiments.multi_island_modular import analyze, calibrate  # noqa: E402
from experiments.multi_island_modular.analyze_hard_active import (  # noqa: E402
    assembled_score,
)


def _target(seed: str, blocks: int = 16, width: int = 8) -> str:
    return "".join(target_bits(seed, block, width) for block in range(blocks))


@pytest.mark.parametrize(
    ("mode", "seed"),
    [
        ("smooth", "69ec5f5f47ee2b7193ecbdf288827ef165eef3bc257b906308cc784f533955e4"),
        ("rugged", "4ad614f0e1317ebaecb2efb3bde2cc2508df48c0d2f745700b2bb7628cc8bf44"),
    ],
)
def test_hidden_target_is_exact_optimum_and_zero_is_not(mode: str, seed: str) -> None:
    target = _target(seed)
    target_score, target_modules, target_exact_blocks, target_pairs = evaluate_candidate(
        target, mode=mode, seed=seed, blocks=16, width=8
    )
    zero_score, _, zero_exact_blocks, zero_pairs = evaluate_candidate(
        "0" * 128, mode=mode, seed=seed, blocks=16, width=8
    )
    assert target_score == pytest.approx(1.0)
    assert target_modules == [1.0] * 16
    assert target_exact_blocks == 16
    assert target_pairs == 15
    assert target_score > zero_score
    assert zero_exact_blocks == 0
    assert zero_pairs == 0


def test_rugged_zero_is_a_strict_one_bit_trap() -> None:
    seed = "4ad614f0e1317ebaecb2efb3bde2cc2508df48c0d2f745700b2bb7628cc8bf44"
    zero_score, _, _, _ = evaluate_candidate("0" * 128, mode="rugged", seed=seed, blocks=16, width=8)
    for index in range(128):
        candidate = list("0" * 128)
        candidate[index] = "1"
        score, _, _, _ = evaluate_candidate("".join(candidate), mode="rugged", seed=seed, blocks=16, width=8)
        assert score < zero_score


def test_calibration_reports_budget_curve() -> None:
    path = ROOT / "experiments/multi_island_modular/tasks/modular_landscape/taskdata/rugged_modular128.json"
    result = calibrate.calibrate(path, [64, 128], samples=20)
    assert result["exact_optimum_score"] == pytest.approx(1.0)
    assert [row["budget"] for row in result["module_discovery_curve"]] == [64, 128]
    assert result["zero_score"] > result["random_mean"]


def test_modular_analyzer_difference_bootstrap_is_centered() -> None:
    low, high = analyze.bootstrap_difference([1.0, 1.1], [0.2, 0.3], "test")
    assert low > 0.0
    assert high > low


def test_active_module_rugged_feedback_is_an_equality_query() -> None:
    seed = "b2a3a1fc6d05c7d9d79c4b5a2e8d08f22fb98d2af8dca5f5ff8d38d24f12b8e7"
    target = rugged_target(seed, 0, 8)
    assert target in CODEBOOK
    assert active_score(target, mode="rugged", target=target) == 1.0
    assert active_score("0" * 8, mode="rugged", target=target) == 0.72
    assert active_score("11111111", mode="rugged", target=target) == 0.45


def test_hard_task_has_wider_artifact_and_seed_bundle() -> None:
    assert HARD_BLOCKS == 16
    assert HARD_WIDTH == 16
    bundle = ROOT / "experiments/multi_island_modular/tasks/hard_active_modular_landscape/taskdata/hard_seed_bundle.json"
    assert len(json.loads(bundle.read_text())["seeds"]) == 8


def test_hard_assembly_requires_provenance_for_exact_modules() -> None:
    seed = json.loads(
        (ROOT / "experiments/multi_island_modular/tasks/hard_active_modular_landscape/taskdata/hard_seed_bundle.json").read_text()
    )["seeds"][0]
    target = hard_target_bits(seed, 0, HARD_WIDTH)
    candidate = target + "0" * (HARD_BLOCKS * HARD_WIDTH - HARD_WIDTH)
    unbacked = assembled_score(candidate, "smooth_hard256", seed, {})
    backed = assembled_score(candidate, "smooth_hard256", seed, {0: target})
    assert unbacked[1:] == (0, 0)
    assert backed[1:] == (1, 0)


def test_hard_rugged_codebook_is_public_but_target_is_not_trap() -> None:
    seed = json.loads(
        (ROOT / "experiments/multi_island_modular/tasks/hard_active_modular_landscape/taskdata/hard_seed_bundle.json").read_text()
    )["seeds"][0]
    target = hard_rugged_target(seed, 0, HARD_WIDTH)
    assert len(HARD_CODEBOOK) == 256
    assert target in HARD_CODEBOOK
    assert hard_active_score("0" * HARD_WIDTH, mode="rugged", target=target) == 0.72
    assert hard_active_score(target, mode="rugged", target=target) == 1.0
