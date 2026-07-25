"""Tests for the v8 certified-composition threshold package."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRADER_FILE = ROOT / "experiments/multi_island_modular/tasks/hard_active_modular_landscape_v8/grader/src/hard_active_modular_landscape_v8_grader/grader.py"
TASKDATA = ROOT / "experiments/multi_island_modular/tasks/hard_active_modular_landscape_v8/taskdata/hard_v8_seed_bundle.json"
SPEC = importlib.util.spec_from_file_location("hard_v8_grader_under_test", GRADER_FILE)
assert SPEC is not None and SPEC.loader is not None
GRADER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GRADER)


def candidate_source(
    modules: list[str],
    active: int = 0,
    certificates: list[str | None] | None = None,
) -> str:
    certificates = certificates or [None] * GRADER.BLOCKS
    module_literals = ",\n".join(f'    "{module}"' for module in modules)
    certificate_literals = ",\n".join(f"    {token!r}" for token in certificates)
    return (
        f"CANDIDATE = (\n{module_literals}\n)\n"
        f"ACTIVE_MODULE = {active}\n"
        f"CERTIFICATES = (\n{certificate_literals}\n)\n"
    )


def evaluate(
    tmp_path: Path,
    modules: list[str],
    *,
    mode: str,
    active: int = 0,
    certificates: list[str | None] | None = None,
    label: str = "eval",
):
    from coral.config import GraderConfig
    from coral.types import Task

    private = tmp_path / f"private-{label}"
    codebase = tmp_path / f"codebase-{label}"
    private.mkdir()
    codebase.mkdir()
    shutil.copy(TASKDATA, private / "hard_v8_seed_bundle.json")
    (codebase / "candidate.py").write_text(
        candidate_source(modules, active, certificates)
    )
    grader = GRADER.Grader(
        GraderConfig(
            args={
                "program_file": "candidate.py",
                "seed_bundle_file": "hard_v8_seed_bundle.json",
                "seed_index": 0,
                "mode": mode,
            }
        )
    )
    grader.private_dir = str(private)
    grader.codebase_path = str(codebase)
    grader.tasks = [Task(id="v8", name="v8", description="smoke")]
    return grader.evaluate()


def explanation(result) -> dict[str, object]:
    text = result.scores["eval"].explanation
    assert text is not None
    return json.loads(text)


def test_v8_dimensions_parser_and_task_variants(tmp_path: Path) -> None:
    from coral.config import CoralConfig

    modules = ["0" * GRADER.WIDTH for _ in range(GRADER.BLOCKS)]
    path = tmp_path / "candidate.py"
    path.write_text(candidate_source(modules, active=31))
    parsed, active, certificates = GRADER.parse_candidate(path)
    assert len(parsed) == GRADER.BLOCKS == 32
    assert sum(map(len, parsed)) == GRADER.TOTAL_WIDTH == 1024
    assert GRADER.WIDTH == 32
    assert GRADER.GROUP_WIDTH == 8
    assert active == 31
    assert certificates == (None,) * GRADER.BLOCKS

    task_dir = ROOT / "experiments/multi_island_modular/tasks/hard_active_modular_landscape_v8"
    for name in ("task.yaml", "task_smooth_v8.yaml", "task_rugged_v8.yaml"):
        config = CoralConfig.from_yaml(task_dir / name)
        assert config.task.tips
        assert config.grader.direction == "maximize"


def test_v8_uncertified_inactive_bits_are_not_an_oracle(tmp_path: Path) -> None:
    seed = json.loads(TASKDATA.read_text())["seeds"][0]
    zero = ["0" * GRADER.WIDTH for _ in range(GRADER.BLOCKS)]
    inactive_exact = zero.copy()
    inactive_exact[1] = GRADER.target_bits(seed, 1)
    baseline = evaluate(tmp_path, zero, mode="smooth", label="baseline")
    changed = evaluate(tmp_path, inactive_exact, mode="smooth", label="inactive")
    assert baseline.aggregated == changed.aggregated
    assert explanation(baseline)["verified_count"] == 0
    assert explanation(changed)["verified_count"] == 0


def test_v8_exact_certificate_is_portable_and_bit_bound(tmp_path: Path) -> None:
    seed = json.loads(TASKDATA.read_text())["seeds"][0]
    modules = ["0" * GRADER.WIDTH for _ in range(GRADER.BLOCKS)]
    modules[0] = GRADER.target_bits(seed, 0)
    exact = evaluate(tmp_path, modules, mode="smooth", active=0, label="exact")
    payload = explanation(exact)
    token = payload["certificate"]
    assert payload["tested"] is True
    assert payload["verified_count"] == 1
    assert token == GRADER.certificate_for(seed, "smooth", 0, modules[0])

    certificates = [None] * GRADER.BLOCKS
    certificates[0] = str(token)
    carried = evaluate(
        tmp_path,
        modules,
        mode="smooth",
        active=1,
        certificates=certificates,
        label="carried",
    )
    assert explanation(carried)["verified_count"] == 1

    broken = modules.copy()
    broken[0] = "0" * GRADER.WIDTH
    invalid = evaluate(
        tmp_path,
        broken,
        mode="smooth",
        active=1,
        certificates=certificates,
        label="broken",
    )
    assert invalid.aggregated == 0.0
    assert "certificate for module 0" in str(explanation(invalid)["invalid_candidate"])


def test_v8_rugged_groups_have_decoy_and_many_local_maxima() -> None:
    seed = json.loads(TASKDATA.read_text())["seeds"][0]
    target = GRADER.target_bits(seed, 0)
    group_target = target[: GRADER.GROUP_WIDTH]
    decoy = "".join("1" if bit == "0" else "0" for bit in group_target)
    assert GRADER.rugged_group_score(seed, 0, 0, group_target) == 1.0
    assert GRADER.rugged_group_score(seed, 0, 0, decoy) == 0.90
    scores = {
        value: GRADER.rugged_group_score(seed, 0, 0, f"{value:08b}")
        for value in range(256)
    }
    maxima = [
        value
        for value, score in scores.items()
        if score > max(scores[value ^ (1 << bit)] for bit in range(8))
    ]
    assert len(maxima) >= 10
    assert int(decoy, 2) in maxima
    assert GRADER.active_score(target, mode="rugged", seed=seed, block=0) == 1.0


def test_v8_simulator_brackets_post_migration_threshold() -> None:
    from experiments.multi_island_modular import simulate_hard_v8 as simulator

    rows = simulator.table()
    simulator.assert_treatment_sensitivity(rows)
    indexed = {
        (row["mode"], row["budget"], row["condition"]): row for row in rows
    }
    assert indexed[("smooth", 384, "multi_island")][
        "best_submitted_certified_blocks"
    ] == indexed[("smooth", 384, "partition")]["best_submitted_certified_blocks"]
    assert indexed[("smooth", 512, "multi_island")][
        "best_submitted_certified_blocks"
    ] > indexed[("smooth", 512, "partition")]["best_submitted_certified_blocks"]
    assert indexed[("rugged", 10240, "multi_island")][
        "best_submitted_certified_blocks"
    ] == indexed[("rugged", 10240, "partition")]["best_submitted_certified_blocks"]
    assert indexed[("rugged", 12288, "multi_island")][
        "best_submitted_certified_blocks"
    ] > indexed[("rugged", 12288, "partition")]["best_submitted_certified_blocks"]


def test_v8_calibration_and_runner_are_registered(tmp_path: Path) -> None:
    from experiments.multi_island_modular import analyze_hard_v8 as analyzer
    from experiments.multi_island_modular import run_hard_v8 as runner

    calibration = json.loads(
        (ROOT / "experiments/multi_island_modular/hard_v8_calibration.json").read_text()
    )
    assert calibration["full_artifact_cost_upper_bound"] == {
        "smooth": 1088,
        "rugged": 32800,
    }
    assert calibration["budgets"]["smooth"] == list(runner.BUDGETS["smooth"])
    assert calibration["budgets"]["rugged"] == list(runner.BUDGETS["rugged"])
    assert min(row["rugged_group_local_maxima_min"] for row in calibration["per_seed"]) >= 2

    runner.base.EXPECTED_REAL_ATTEMPTS = 512
    command = runner.build_command(
        runner.base.TASKS["smooth_certified_v8"],
        "multi_island",
        tmp_path / "rep-01",
    )
    assert "agents.count=8" in command
    assert "agents.timeout=300" in command
    assert "agents.sandbox.network=allowlist" in command
    assert 'agents.sandbox.allowed_domains=["api.appintheloop.com"]' in command
    assert "islands.migration.every=128" in command
    assert "run.stop.max_real_attempts_per_agent=64" in command
    assert "grader.args.seed_index=0" in command
    assert "grader.args.mode=smooth" in command
    assert f"agents.heartbeat={analyzer.heartbeat_for('smooth')}" in command


def _record(
    commit: str,
    origin: str,
    score: float,
    payload: dict[str, object],
    sequence: int,
) -> dict[str, object]:
    return {
        "commit_hash": commit,
        "agent_id": f"agent-{sequence}",
        "score": score,
        "timestamp": str(sequence),
        "feedback": f"eval: {json.dumps(payload)}",
        "metadata": {"budget_class": "real", "origin_island_id": origin},
    }


def test_v8_analyzer_primary_is_submitted_artifact_not_pool(monkeypatch, tmp_path: Path) -> None:
    from experiments.multi_island_modular import analyze_hard_v8 as analyzer

    seed = json.loads(TASKDATA.read_text())["seeds"][0]
    zero = ["0" * GRADER.WIDTH for _ in range(GRADER.BLOCKS)]
    target0 = GRADER.target_bits(seed, 0)
    target1 = GRADER.target_bits(seed, 1)
    cert0 = GRADER.certificate_for(seed, "smooth", 0, target0)
    cert1 = GRADER.certificate_for(seed, "smooth", 1, target1)
    sources: dict[str, str] = {}

    first = zero.copy()
    first[0] = target0
    sources["a-exact"] = candidate_source(first, 0)
    records = [
        _record(
            "a-exact",
            "atlantis",
            GRADER.ACTIVE_WEIGHT + GRADER.ASSEMBLY_WEIGHT / GRADER.BLOCKS,
            {
                "active_module": 0,
                "active_score": 1.0,
                "tested": True,
                "certificate": cert0,
                "verified_count": 1,
            },
            1,
        )
    ]

    second = zero.copy()
    second[1] = target1
    sources["b-exact"] = candidate_source(second, 1)
    records.append(
        _record(
            "b-exact",
            "avalon",
            GRADER.ACTIVE_WEIGHT + GRADER.ASSEMBLY_WEIGHT / GRADER.BLOCKS,
            {
                "active_module": 1,
                "active_score": 1.0,
                "tested": True,
                "certificate": cert1,
                "verified_count": 1,
            },
            2,
        )
    )
    monkeypatch.setattr(analyzer.common, "real_records", lambda _run_dir: records)
    monkeypatch.setattr(
        analyzer.common,
        "source_at",
        lambda _run_dir, commit: sources[commit],
    )
    partition = analyzer.collect(
        tmp_path,
        {"condition": "partition", "repetition": 1},
        "smooth_certified_v8",
        budget=2,
    )
    assert partition["global_discovered_blocks"] == 2
    assert partition["best_submitted_certified_blocks"] == 1
    assert partition["pooled_tested_blocks"] == 2

    combined = zero.copy()
    combined[0] = target0
    combined[1] = target1
    certificates = [None] * GRADER.BLOCKS
    certificates[0] = cert0
    certificates[1] = cert1
    sources["combined"] = candidate_source(combined, 2, certificates)
    active_score = GRADER.active_score(
        combined[2], mode="smooth", seed=seed, block=2
    )
    records.append(
        _record(
            "combined",
            "avalon",
            GRADER.ACTIVE_WEIGHT * active_score
            + GRADER.ASSEMBLY_WEIGHT * 2 / GRADER.BLOCKS,
            {
                "active_module": 2,
                "active_score": round(active_score, 8),
                "tested": False,
                "certificate": None,
                "verified_count": 2,
            },
            3,
        )
    )
    multi = analyzer.collect(
        tmp_path,
        {"condition": "multi_island", "repetition": 1},
        "smooth_certified_v8",
        budget=3,
    )
    assert multi["best_submitted_certified_blocks"] == 2
    assert multi["transferred_blocks"] == 1
    assert multi["first_transfer_eval"] == 3
