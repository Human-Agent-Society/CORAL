"""Real-task multi-island scaling experiment configuration."""

from __future__ import annotations

import gzip
import json
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


def _resolved_wall_command(
    condition: str, agents: int, task: str = "kernel"
) -> tuple[list[str], CoralConfig]:
    spec = runner.TASKS[task]
    command = runner.build_command(
        spec,
        condition,
        agents,
        per_agent_budget=2,
        results_root=Path("/var/tmp/scaling-wall-test"),
        run_dir=Path("/var/tmp/scaling-wall-test/run"),
        gateway_port=43210,
        wall_clock_seconds=1800,
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


def test_scaling_sqrt_island_uses_rounded_sqrt_population() -> None:
    _command, config = _resolved_command("sqrt_island", agents=32)

    assert runner.island_count_for("sqrt_island", 32) == 6
    assert config.islands.count == 6
    assert config.islands.migration.enabled is True
    assert config.islands.migration.every == 32
    assert config.islands.migration.rank_window == 32
    assert config.islands.migration.max_per_cycle == 6
    assert config.islands.migration.remigration_cooldown == 32


def test_scaling_wall_clock_command_uses_fixed_time_without_eval_quota() -> None:
    command, config = _resolved_wall_command("multi_island", agents=8)

    assert "run.stop.wall_clock_seconds=1800" in command
    assert "run.stop.max_real_attempts" not in " ".join(command)
    assert config.run.stop.wall_clock_seconds == 1800
    assert config.run.stop.max_real_attempts is None
    assert config.run.stop.max_real_attempts_per_agent is None
    assert "fixed 30.0-minute wall-clock window" in config.task.tips


def test_wall_clock_completion_can_be_checked_before_writing_operator_result(
    tmp_path: Path,
) -> None:
    public = tmp_path / ".coral/public"
    attempts = public / "attempts"
    attempts.mkdir(parents=True)
    (public / "auto_stop.json").write_text(
        json.dumps(
            {
                "reason": "wall_clock",
                "wall_clock_seconds": 3600,
                "elapsed_wall_seconds": 3600.01,
            }
        )
        + "\n"
    )
    (attempts / "a.json").write_text(
        json.dumps(
            {
                "commit_hash": "a" * 40,
                "status": "improved",
                "score": 5351,
                "metadata": {"budget_class": "real"},
            }
        )
        + "\n"
    )

    assert not runner.is_complete(tmp_path, None, wall_clock_seconds=3600)
    assert runner.is_complete(
        tmp_path,
        None,
        wall_clock_seconds=3600,
        require_operator_result=False,
    )
    (tmp_path / "operator-result.json").write_text(
        json.dumps({"status": "complete", "timed_out": False}) + "\n"
    )
    assert runner.is_complete(tmp_path, None, wall_clock_seconds=3600)

    (tmp_path / "operator-result.json").write_text(
        json.dumps({"status": "failed", "timed_out": False}) + "\n"
    )
    assert not runner.is_complete(tmp_path, None, wall_clock_seconds=3600)


def test_wall_clock_completion_rejects_wrong_or_unelapsed_budget(tmp_path: Path) -> None:
    public = tmp_path / ".coral/public"
    attempts = public / "attempts"
    attempts.mkdir(parents=True)
    (attempts / "a.json").write_text(
        json.dumps(
            {
                "commit_hash": "a" * 40,
                "status": "improved",
                "score": 5351,
                "metadata": {"budget_class": "real"},
            }
        )
        + "\n"
    )
    marker = public / "auto_stop.json"
    marker.write_text(
        json.dumps(
            {
                "reason": "wall_clock",
                "wall_clock_seconds": 1800,
                "elapsed_wall_seconds": 3600,
            }
        )
        + "\n"
    )
    assert not runner.is_complete(
        tmp_path,
        None,
        wall_clock_seconds=3600,
        require_operator_result=False,
    )
    assert not analysis.wall_clock_stop_matches(json.loads(marker.read_text()), 3600)

    marker.write_text(
        json.dumps(
            {
                "reason": "wall_clock",
                "wall_clock_seconds": 3600,
                "elapsed_wall_seconds": 3599.99,
            }
        )
        + "\n"
    )
    assert not runner.is_complete(
        tmp_path,
        None,
        wall_clock_seconds=3600,
        require_operator_result=False,
    )
    assert not analysis.wall_clock_stop_matches(json.loads(marker.read_text()), 3600)


def test_scaling_analysis_only_rejects_executed_protocol_violations(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / ".coral/public/logs/agent.0.log"
    log_path.parent.mkdir(parents=True)
    event = {
        "type": "tool_use",
        "part": {
            "tool": "bash",
            "state": {
                "status": "error",
                "input": {"command": "grep -rn coreid /jfs-host/checkout"},
            },
        },
    }
    log_path.write_text(json.dumps(event) + "\n")
    assert not analysis.executed_protocol_violation(tmp_path)

    event["part"]["state"]["status"] = "completed"
    log_path.write_text(json.dumps(event) + "\n")
    assert analysis.executed_protocol_violation(tmp_path)
    assert analysis.protocol_invalid(tmp_path)

    event["part"]["state"]["input"]["command"] = "ls /home"
    log_path.write_text(json.dumps(event) + "\n")
    assert analysis.executed_protocol_violation(tmp_path)


def test_scaling_analysis_rejects_all_forbidden_executed_tools(tmp_path: Path) -> None:
    log_path = tmp_path / ".coral/public/logs/agent.0.log"
    log_path.parent.mkdir(parents=True)
    events = [
        {
            "type": "tool_use",
            "part": {
                "tool": "bash",
                "state": {
                    "status": "completed",
                    "input": {"command": "find .opencode -name '*.json'"},
                },
            },
        },
        {
            "type": "tool_use",
            "part": {
                "tool": "glob",
                "state": {"status": "completed", "input": {"pattern": "**/*"}},
            },
        },
        {
            "type": "tool_use",
            "part": {
                "tool": "task",
                "state": {"status": "completed", "input": {"prompt": "delegate"}},
            },
        },
        {
            "type": "tool_use",
            "part": {
                "tool": "bash",
                "state": {
                    "status": "completed",
                    "input": {"command": "coral eval -m benchmark --tune"},
                },
            },
        },
        {
            "type": "tool_use",
            "part": {
                "tool": "read",
                "state": {
                    "status": "completed",
                    "input": {"filePath": ".coral/private/answer.json"},
                },
            },
        },
    ]
    for event in events:
        log_path.write_text(json.dumps(event) + "\n")
        assert analysis.executed_protocol_violation(tmp_path)


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


def test_scaling_analysis_expects_all_32_cells() -> None:
    identities = analysis.expected_cell_identities({1})

    assert len(identities) == 32
    assert ("kernel", "global", 1, 1) in identities
    assert ("kernel", "multi_island", 1, 1) not in identities
    assert ("polyominoes", "multi_island", 32, 1) in identities
    assert ("polyominoes", "sqrt_island", 32, 1) in identities


def test_scaling_analysis_sums_gateway_token_usage(tmp_path: Path) -> None:
    log_path = tmp_path / ".coral/public/gateway/requests.jsonl"
    log_path.parent.mkdir(parents=True)
    records = [
        {
            "response": {
                "usage": {
                    "input_tokens": 100,
                    "input_tokens_details": {"cached_tokens": 80},
                    "output_tokens": 12,
                    "total_tokens": 112,
                }
            }
        },
        {"status_code": 500, "response": {"error": "provider error"}},
        {
            "response": {
                "usage": {
                    "input_tokens": 50,
                    "output_tokens": 7,
                    "total_tokens": 57,
                }
            }
        },
    ]
    log_path.write_text("\n".join(json.dumps(record) for record in records) + "\n")

    assert analysis.gateway_usage(tmp_path) == {
        "model_requests": 3,
        "input_tokens": 150,
        "cached_input_tokens": 80,
        "output_tokens": 19,
        "total_tokens": 169,
    }


def test_scaling_analysis_reads_compressed_gateway_usage(tmp_path: Path) -> None:
    log_path = tmp_path / ".coral/public/gateway/requests.jsonl.gz"
    log_path.parent.mkdir(parents=True)
    record = {
        "response": {
            "usage": {
                "input_tokens": 11,
                "input_tokens_details": {"cached_tokens": 7},
                "output_tokens": 5,
                "total_tokens": 16,
            }
        }
    }
    with gzip.open(log_path, mode="wt") as handle:
        handle.write(json.dumps(record) + "\n")

    assert analysis.gateway_usage(tmp_path) == {
        "model_requests": 1,
        "input_tokens": 11,
        "cached_input_tokens": 7,
        "output_tokens": 5,
        "total_tokens": 16,
    }


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
