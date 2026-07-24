"""Tests for the independent v5 high-dimensional modular package."""

from __future__ import annotations

import importlib.util
import json
import sys
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


def test_v5_analysis_does_not_credit_future_provenance(monkeypatch, tmp_path: Path) -> None:
    """An early lucky artifact must not gain credit from later exact probes."""
    # The v3/v5 grader packages share an import name.  This test needs the
    # analyzer's v4 package, so remove the module loaded by the grader checks
    # above before importing the analyzer.
    sys.modules.pop("hard_active_modular_landscape_grader", None)
    sys.modules.pop("hard_active_modular_landscape_grader.grader", None)
    from experiments.multi_island_modular import analyze_hard_v4 as analyzer

    seed = str(json.loads(TASKDATA.read_text())["seeds"][0])
    targets = [analyzer.target_bits(seed, block, analyzer.WIDTH) for block in range(analyzer.BLOCKS)]
    zero = "0" * analyzer.WIDTH

    def source(modules: list[str], active: int) -> str:
        literals = ",\n".join(f'    "{module}"' for module in modules)
        return f"CANDIDATE = (\n{literals}\n)\nACTIVE_MODULE = {active}\n"

    # The first candidate contains both future target modules, but neither has
    # been tested.  The next two records test those modules separately and do
    # not carry the other exact module, so a retroactive ledger would wrongly
    # make the first candidate look like the best assembled artifact.
    early_modules = targets[:2] + [zero] * (analyzer.BLOCKS - 2)
    module_zero = [targets[0], zero] + [zero] * (analyzer.BLOCKS - 2)
    module_one = [zero, targets[1]] + [zero] * (analyzer.BLOCKS - 2)
    sources = {
        "early": source(early_modules, 2),
        "zero": source(module_zero, 0),
        "one": source(module_one, 1),
    }
    records = [
        {"commit_hash": "early", "score": 0.5, "timestamp": "1", "metadata": {"budget_class": "real"}},
        {"commit_hash": "zero", "score": 1.0, "timestamp": "2", "metadata": {"budget_class": "real"}},
        {"commit_hash": "one", "score": 1.0, "timestamp": "3", "metadata": {"budget_class": "real"}},
    ]
    monkeypatch.setattr(analyzer, "real_records", lambda _run_dir: records)
    monkeypatch.setattr(analyzer, "source_at", lambda _run_dir, commit: sources[commit])

    row = analyzer.collect(
        tmp_path,
        {"condition": "global", "repetition": 1},
        "smooth_hard_v5",
        budget=3,
    )

    assert row["final_known_blocks"] == 2
    assert row["pooled_tested_blocks"] == 2
    assert row["best_tested_blocks"] == 1
