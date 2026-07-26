from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_window_followup_registration_binds_blind_sources() -> None:
    directory = ROOT / "experiments/multi_island_hard"
    registration = json.loads(
        (directory / "threshold_v6_extreme_window_followup_registration.json").read_text()
    )
    assert registration["outcome_aware_sequential_followup"] is True
    assert registration["not_a_replacement_for_original_confirmation"] is True
    assert registration["result_roots_absent_at_registration"] == {
        "raw": True,
        "analysis": True,
        "checkpoint": True,
    }
    for filename, expected in registration["artifacts"].items():
        observed = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
        assert observed == expected


def test_window_followup_seeds_are_fresh() -> None:
    from experiments.multi_island_hard import run_threshold_v6_extreme_window_followup as runner

    seeds = tuple(runner.followup_seed(block) for block in range(runner.FOLLOWUP_BLOCKS))
    runner.validate_seed_isolation(seeds)
    assert len(set(map(runner.seed_sha256, seeds))) == runner.FOLLOWUP_BLOCKS


def test_window_followup_reduced_run_is_deterministic_and_audited(tmp_path: Path) -> None:
    from experiments.multi_island_hard import analyze_threshold_v6_extreme_window_followup as analyzer
    from experiments.multi_island_hard import run_threshold_v6_extreme_window_followup as runner

    kwargs = {
        "cells": ((2, 32),),
        "blocks": 2,
        "reference_samples": 16,
        "max_workers": 1,
        "checkpoint": tmp_path / "checkpoint.json",
        "checkpoint_every": 24,
        "fully_registered_run": False,
    }
    first = runner.run_resumable(**kwargs)
    second = runner.run_resumable(**kwargs)
    assert first == second
    assert analyzer.audit(first, require_registered=False) == []
    result = analyzer.analyze(first, require_registered=False, bootstrap_repetitions=2_000)
    assert result["audit_passes"] is True
    assert len(result["cells"]) == 1
    assert result["cells"][0]["k"] == 2


def test_window_followup_checkpoint_rejects_drift(tmp_path: Path) -> None:
    from experiments.multi_island_hard import run_threshold_v6_extreme_window_followup as runner

    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": runner.CHECKPOINT_SCHEMA_VERSION,
                "configuration": {"wrong": True},
                "expected_items": 1,
                "completed_items": 0,
                "complete": False,
                "completed": {},
            }
        )
    )
    items = runner.work_items(cells=((2, 32),), blocks=2)
    expected = runner.configuration(cells=((2, 32),), blocks=2, reference_samples=16)
    with pytest.raises(ValueError, match="configuration drifted"):
        runner.load_checkpoint(checkpoint, expected_configuration=expected, items=items)
