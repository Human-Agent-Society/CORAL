#!/usr/bin/env python3
"""Run a non-inferential 32-evaluation topology canary for threshold v4."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from experiments.multi_island import run_matrix as base
from experiments.multi_island.isolation_audit import require_sandbox_contract
from experiments.multi_island_hard import run_threshold_v4 as runner

CANARY_BUDGET = 32
CANARY_TASKS = (
    runner.SMOOTH_TASK,
    runner.RUGGED_TASKS[runner.registered_selection()["k"]],
)
CANARY_CONDITIONS = ("global_8", "partition_4", "multi_island_4")
RESULTS_ROOT = Path(
    "/var/tmp/coral-institutions-results/nk-threshold-v4-canary/high_diffusion"
)
SCRIPTED_RUNTIME = "experiments.multi_island_hard.scripted_runtime:ScriptedRuntime"
TASKS = {name: runner.TASKS[name] for name in CANARY_TASKS}


def _replace(command: list[str], prefix: str, value: str) -> None:
    for index, item in enumerate(command):
        if item.startswith(prefix):
            command[index] = value
            return
    command.append(value)


def build_command(spec: Any, condition: str, run_dir: Path) -> list[str]:
    if condition not in CANARY_CONDITIONS:
        raise ValueError(f"threshold-v4 canary does not support {condition}")
    command = runner._BASE_BUILD_COMMAND(
        spec,
        condition,
        run_dir,
        topologies=runner.TOPOLOGIES,
    )
    _replace(command, "agents.runtime=", f"agents.runtime={SCRIPTED_RUNTIME}")
    _replace(command, "agents.model=", "agents.model=scripted")
    _replace(command, "agents.sandbox.network=", "agents.sandbox.network=allowlist")
    _replace(command, "agents.count=", "agents.count=8")
    _replace(command, "agents.timeout=", "agents.timeout=0")
    heartbeat = [
        {"name": "reflect", "every": CANARY_BUDGET // 8 + 1},
        {"name": "consolidate", "every": CANARY_BUDGET + 1, "is_global": True},
        {
            "name": "pivot",
            "every": CANARY_BUDGET // 8 + 1,
            "trigger": "plateau",
        },
    ]
    _replace(
        command,
        "agents.heartbeat=",
        "agents.heartbeat=" + json.dumps(heartbeat, separators=(",", ":")),
    )
    _replace(command, "grader.parallel.max_workers=", "grader.parallel.max_workers=4")
    command.append("agents.sandbox.allowed_domains=[]")
    migration_every = 8
    topology = runner.TOPOLOGIES[condition]
    _replace(
        command,
        "islands.migration.every=",
        f"islands.migration.every={migration_every}",
    )
    _replace(
        command,
        "islands.migration.rank_window=",
        f"islands.migration.rank_window={migration_every}",
    )
    _replace(
        command,
        "islands.migration.remigration_cooldown=",
        f"islands.migration.remigration_cooldown={migration_every}",
    )
    _replace(
        command,
        "islands.migration.max_per_cycle=",
        f"islands.migration.max_per_cycle={topology['max_per_cycle']}",
    )
    command.append("islands.migration.dest_weighting=round_robin")
    visible_agents = 8 if condition == "global_8" else 2
    scripted_command = [
        "python3",
        "scripted_search.py",
        "--attempts-per-agent",
        str(CANARY_BUDGET // 8),
        "--visible-agents",
        str(visible_agents),
    ]
    command.append(
        "agents.runtime_options.command="
        + json.dumps(scripted_command, separators=(",", ":"))
    )
    command.append(f"run.stop.max_real_attempts_per_agent={CANARY_BUDGET // 8}")
    command.append(f"grader.args.seed_index={runner.repetition_seed_index(run_dir)}")
    return command


def _fixed_argument(flag: str, values: tuple[str, ...]) -> None:
    observed = runner._argument_values(flag)
    if observed is None:
        sys.argv.extend([flag, *values])
    elif observed != list(values):
        raise SystemExit(f"{flag} must be {' '.join(values)} for the v4 canary")


def main() -> int:
    try:
        require_sandbox_contract()
        runner.require_seed_contract()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    _fixed_argument("--budget", (str(CANARY_BUDGET),))
    _fixed_argument("--tasks", CANARY_TASKS)
    _fixed_argument("--conditions", CANARY_CONDITIONS)
    _fixed_argument("--repetitions", ("1",))
    previous = (
        base.TASKS,
        base.TOPOLOGIES,
        base.DEFAULT_RESULTS_ROOT,
        base.build_command,
        base.EXPECTED_REAL_ATTEMPTS,
    )
    base.TASKS = TASKS
    base.TOPOLOGIES = runner.TOPOLOGIES
    base.DEFAULT_RESULTS_ROOT = RESULTS_ROOT
    base.build_command = build_command
    try:
        return base.main()
    finally:
        (
            base.TASKS,
            base.TOPOLOGIES,
            base.DEFAULT_RESULTS_ROOT,
            base.build_command,
            base.EXPECTED_REAL_ATTEMPTS,
        ) = previous


if __name__ == "__main__":
    raise SystemExit(main())
