#!/usr/bin/env python3
"""Run the held-out N=128 Smooth/Rugged boundary threshold matrix."""

from __future__ import annotations

import sys
from pathlib import Path

from experiments.multi_island import run_matrix as base

ROOT = Path(__file__).resolve().parent
TASK_DIR = ROOT / "tasks/institutional_landscape"
ROLE_FILE = ROOT / "threshold_v2_protocol.md"
BUDGETS = (128, 256, 512, 1024, 2048, 4096)
MODEL_API_DOMAINS = ("api.appintheloop.com",)

base.DEFAULT_RESULTS_ROOT = Path("/var/tmp/coral-institutions-results/nk-threshold-v2")
base.TOPOLOGIES = {
    "global_8": {"count": 1, "migration": False, "max_per_cycle": 1},
    "partition_4": {"count": 4, "migration": False, "max_per_cycle": 4},
    "multi_island_2": {"count": 2, "migration": True, "max_per_cycle": 2},
    "multi_island_4": {"count": 4, "migration": True, "max_per_cycle": 4},
}
base.TASKS = {
    name: base.TaskSpec(
        name=name,
        config=TASK_DIR / config,
        cwd=TASK_DIR,
        conditions=("global_8", "partition_4", "multi_island_2", "multi_island_4"),
    )
    for name, config in {
        "smooth128_rep_v2": "task_smooth128_replicated_v2.yaml",
        "rugged128_k12_rep_v2": "task_rugged128_k12_replicated_v2.yaml",
    }.items()
}

_BASE_BUILD_COMMAND = base.build_command


def migration_every(budget: int) -> int:
    return max(64, min(512, budget // 4))


def heartbeat_for(budget: int) -> str:
    every = max(32, min(128, budget // 8))
    return (
        f'[{{"name":"reflect","every":{every}}},'
        f'{{"name":"consolidate","every":{every * 2},"is_global":true}},'
        f'{{"name":"pivot","every":{every},"trigger":"plateau"}},'
        f'{{"name":"lint_wiki","every":{every * 2},"is_global":true}}]'
    )


def repetition_seed_index(run_dir: Path) -> int:
    name = run_dir.name.split("-retry-", 1)[0]
    if not name.startswith("rep-"):
        raise ValueError(f"run directory has no repetition index: {run_dir}")
    index = int(name.removeprefix("rep-")) - 1
    if not 0 <= index < 8:
        raise ValueError("threshold v2 supports exactly eight paired seeds")
    return index


def build_command(spec, condition, run_dir):
    command = _BASE_BUILD_COMMAND(spec, condition, run_dir)
    budget = base.EXPECTED_REAL_ATTEMPTS
    if budget not in BUDGETS:
        raise ValueError(f"unregistered threshold-v2 budget: {budget}")
    every = migration_every(budget)
    topology = base.TOPOLOGIES[condition]
    seed_index = repetition_seed_index(run_dir)
    for index, item in enumerate(command):
        if item.startswith("agents.runtime_options.role_file="):
            command[index] = f"agents.runtime_options.role_file={ROLE_FILE}"
        elif item.startswith("agents.sandbox.network="):
            command[index] = "agents.sandbox.network=allowlist"
        elif item.startswith("islands.migration.every="):
            command[index] = f"islands.migration.every={every}"
        elif item.startswith("islands.migration.rank_window="):
            command[index] = f"islands.migration.rank_window={every}"
        elif item.startswith("islands.migration.remigration_cooldown="):
            command[index] = f"islands.migration.remigration_cooldown={every}"
        elif item.startswith("islands.migration.max_per_cycle="):
            command[index] = (
                f"islands.migration.max_per_cycle={topology['max_per_cycle']}"
            )
        elif item.startswith("grader.parallel.max_workers="):
            command[index] = "grader.parallel.max_workers=4"
        elif item == "agents.count=4":
            command[index] = "agents.count=8"
    command.append(f"agents.heartbeat={heartbeat_for(budget)}")
    command.append('agents.sandbox.allowed_domains=["api.appintheloop.com"]')
    command.append("islands.migration.dest_weighting=round_robin")
    command.append(f"run.stop.max_real_attempts_per_agent={budget // 8}")
    command.append(f"grader.args.seed_index={seed_index}")
    return command


def main() -> int:
    if "--budget" not in sys.argv:
        raise SystemExit("threshold v2 requires one explicit registered --budget per launch")
    previous = base.build_command
    base.build_command = build_command
    try:
        return base.main()
    finally:
        base.build_command = previous


if __name__ == "__main__":
    raise SystemExit(main())
