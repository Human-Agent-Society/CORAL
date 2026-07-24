#!/usr/bin/env python3
"""Run the v7 oracle-free high-difficulty threshold matrix."""

from __future__ import annotations

import re
from pathlib import Path

from experiments.multi_island import run_matrix as base

ROOT = Path(__file__).resolve().parent
TASK_DIR = ROOT / "tasks/hard_active_modular_landscape_v7"
ROLE_FILE = ROOT / "hard_v7_eval_protocol.md"

HEARTBEAT_OVERRIDE = (
    '[{"name":"reflect","every":16},'
    '{"name":"consolidate","every":32,"is_global":true},'
    '{"name":"pivot","every":16,"trigger":"plateau"},'
    '{"name":"lint_wiki","every":32,"is_global":true}]'
)

base.DEFAULT_RESULTS_ROOT = Path("/var/tmp/coral-institutions-results/modular-hard-v7")
base.TOPOLOGIES = {
    "global_8": {"count": 1, "migration": False},
    "partition": {"count": 2, "migration": False},
    "multi_island": {"count": 2, "migration": True},
}
base.TASKS = {
    name: base.TaskSpec(
        name=name,
        config=TASK_DIR / config,
        cwd=TASK_DIR,
        conditions=("global_8", "partition", "multi_island"),
    )
    for name, config in {
        "smooth_hard_v7": "task_smooth_v7.yaml",
        "rugged_hard_v7": "task_rugged_v7.yaml",
    }.items()
}

_BASE_BUILD_COMMAND = base.build_command


def migration_every(budget: int) -> int:
    """Allow a meaningful module probe while retaining several transfers."""
    return max(256, min(2048, budget // 4))


def repetition_seed_index(run_dir: Path) -> int:
    match = re.search(r"rep-(\d+)", run_dir.name)
    if match is None:
        raise ValueError(f"run directory has no repetition index: {run_dir}")
    return int(match.group(1)) - 1


def build_command(spec, condition, run_dir):
    command = _BASE_BUILD_COMMAND(spec, condition, run_dir)
    budget = base.EXPECTED_REAL_ATTEMPTS
    if budget % 8:
        raise ValueError("v7 budgets must be divisible by the fixed eight-agent roster")
    every = migration_every(budget)
    seed_index = repetition_seed_index(run_dir)
    for index, item in enumerate(command):
        if item.startswith("agents.runtime_options.role_file="):
            command[index] = f"agents.runtime_options.role_file={ROLE_FILE}"
        elif item.startswith("islands.migration.every="):
            command[index] = f"islands.migration.every={every}"
        elif item.startswith("islands.migration.rank_window="):
            command[index] = f"islands.migration.rank_window={every}"
        elif item.startswith("islands.migration.remigration_cooldown="):
            command[index] = "islands.migration.remigration_cooldown=256"
        elif item.startswith("grader.parallel.max_workers="):
            command[index] = "grader.parallel.max_workers=4"
        elif item == "agents.count=4":
            command[index] = "agents.count=8"
    command.append(f"agents.heartbeat={HEARTBEAT_OVERRIDE}")
    command.append(f"run.stop.max_real_attempts_per_agent={budget // 8}")
    command.append(f"grader.args.seed_index={seed_index}")
    command.append(f"grader.args.mode={'smooth' if spec.name.startswith('smooth_') else 'rugged'}")
    return command


base.build_command = build_command


if __name__ == "__main__":
    raise SystemExit(base.main())
