"""Real-task multi-island scaling experiment configuration."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from coral.config import CoralConfig
from coral.hooks.post_commit import submit_eval
from experiments.multi_island_scaling import analyze_scaling as analysis
from experiments.multi_island_scaling import run_scaling as runner


def _resolved_command(
    condition: str, agents: int, task: str = "kernel"
) -> tuple[list[str], CoralConfig]:
    spec = runner.TASKS[task]
    command = runner.build_command(
        spec,
        condition,
        agents,
        per_agent_budget=2,
        results_root=Path("/var/tmp/scaling-test"),
        run_dir=Path("/var/tmp/scaling-test/run"),
        gateway_port=43210,
    )
    config = CoralConfig.merge_dotlist(CoralConfig.from_yaml(spec.config), command[7:])
    return command, config


def test_scaling_command_uses_minimax_and_equal_per_agent_budget() -> None:
    command, config = _resolved_command("global", agents=8)

    assert "agents.model=openai/MiniMax-M3" in command
    assert config.agents.runtime == "opencode"
    assert config.agents.gateway.enabled is True
    assert config.agents.gateway.port == 43210
    assert config.agents.sandbox.enabled is True
    assert config.agents.runtime_options["disable_subagents"] is True
    assert config.agents.runtime_options["disable_file_discovery"] is True
    assert config.run.stop.max_real_attempts == 16
    assert config.run.stop.max_real_attempts_per_agent == 2
    assert "Controlled scaling experiment protocol" in config.task.tips


def test_scaling_multi_island_treatment_changes_only_topology_knobs() -> None:
    _command, config = _resolved_command("multi_island", agents=8)

    assert config.islands.count == 2
    assert config.islands.migration.enabled is True
    assert config.islands.migration.every == 8
    assert config.islands.migration.rank_window == 8
    assert config.islands.migration.min_evals == 1
    assert config.islands.migration.remigration_cooldown == 8


def test_single_agent_multi_island_cell_is_not_scheduled() -> None:
    args = SimpleNamespace(
        tasks=["kernel"],
        conditions=["global", "multi_island"],
        agent_counts=[1, 2],
        repetitions=1,
    )

    cells = [
        (spec.name, condition, count, repetition)
        for spec, condition, count, repetition in runner.ordered_cells(args)
    ]

    assert cells == [
        ("kernel", "global", 1, 1),
        ("kernel", "global", 2, 1),
        ("kernel", "multi_island", 2, 1),
    ]


def test_polyominoes_uses_private_local_evaluator() -> None:
    _command, config = _resolved_command("global", agents=2, task="polyominoes")

    assert config.grader.entrypoint == "scaling_poly_grader.grader:Grader"
    assert any("poly_grader" in command for command in config.grader.setup)
    assert any("provision_poly_data.py" in command for command in config.grader.setup)
    assert not any("Frontier-CS.git" in command for command in config.grader.setup)


def test_scaling_admission_rejects_tune_mode(monkeypatch) -> None:
    monkeypatch.setenv("CORAL_DISABLE_TUNE", "1")

    try:
        submit_eval("should not be submitted", "agent", tune=True)
    except RuntimeError as exc:
        assert "tune-mode" in str(exc)
    else:  # pragma: no cover - defensive assertion for the admission guard
        raise AssertionError("tune mode was admitted despite the experiment guard")


def test_scaling_analysis_expects_all_22_cells() -> None:
    identities = analysis.expected_cell_identities({1})

    assert len(identities) == 22
    assert ("kernel", "global", 1, 1) in identities
    assert ("kernel", "multi_island", 1, 1) not in identities
    assert ("polyominoes", "multi_island", 32, 1) in identities


def test_scaling_analysis_selects_latest_complete_run_once() -> None:
    common = {
        "task": "kernel",
        "condition": "global",
        "agent_count": 2,
        "repetition": 1,
        "protocol_valid": True,
        "valid_scored_attempts": 2,
        "complete": True,
    }
    rows = [
        {
            **common,
            "run_dir": "/results/rep-01-retry-02",
            "_finished_at": "2026-07-31T10:56:12+00:00",
        },
        {
            **common,
            "run_dir": "/results/rep-01",
            "_finished_at": "2026-07-31T20:36:49+00:00",
        },
        {
            **common,
            "run_dir": "/results/rep-01-retry-03",
            "_finished_at": "2026-07-31T21:00:00+00:00",
            "complete": False,
        },
    ]

    selected, superseded, ineligible = analysis.select_complete_cells(rows)

    assert [row["run_dir"] for row in selected] == ["/results/rep-01"]
    assert superseded == 1
    assert ineligible == 1
