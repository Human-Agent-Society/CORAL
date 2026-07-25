#!/usr/bin/env python3
"""Run the v8 certified-composition threshold matrix."""

from __future__ import annotations

import sys
from pathlib import Path

from experiments.multi_island import run_matrix as base
from experiments.multi_island_modular.simulate_hard_v8 import BUDGETS, MIGRATION_EVERY

ROOT = Path(__file__).resolve().parent
TASK_DIR = ROOT / "tasks/hard_active_modular_landscape_v8"
ROLE_FILE = ROOT / "hard_v8_eval_protocol.md"

base.DEFAULT_RESULTS_ROOT = Path("/var/tmp/coral-institutions-results/modular-hard-v8")
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
        "smooth_certified_v8": "task_smooth_v8.yaml",
        "rugged_certified_v8": "task_rugged_v8.yaml",
    }.items()
}

_BASE_BUILD_COMMAND = base.build_command


def mode_for(task_name: str) -> str:
    return "smooth" if task_name.startswith("smooth_") else "rugged"


def heartbeat_for(mode: str) -> str:
    every = 64 if mode == "smooth" else 512
    consolidate = every * 2
    return (
        f'[{{"name":"reflect","every":{every}}},'
        f'{{"name":"consolidate","every":{consolidate},"is_global":true}},'
        f'{{"name":"pivot","every":{every},"trigger":"plateau"}},'
        f'{{"name":"lint_wiki","every":{consolidate},"is_global":true}}]'
    )


def repetition_seed_index(run_dir: Path) -> int:
    name = run_dir.name.split("-retry-", 1)[0]
    if not name.startswith("rep-"):
        raise ValueError(f"run directory has no repetition index: {run_dir}")
    index = int(name.removeprefix("rep-")) - 1
    if not 0 <= index < 8:
        raise ValueError("v8 supports exactly eight paired private seeds")
    return index


def build_command(spec, condition, run_dir):
    command = _BASE_BUILD_COMMAND(spec, condition, run_dir)
    budget = base.EXPECTED_REAL_ATTEMPTS
    mode = mode_for(spec.name)
    if budget not in BUDGETS[mode]:
        raise ValueError(f"unregistered {mode} v8 budget: {budget}")
    if budget % 8:
        raise ValueError("v8 budgets must divide evenly across eight agents")
    every = MIGRATION_EVERY[mode]
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
        elif item.startswith("grader.parallel.max_workers="):
            command[index] = "grader.parallel.max_workers=4"
        elif item == "agents.count=4":
            command[index] = "agents.count=8"
    command.append(f"agents.heartbeat={heartbeat_for(mode)}")
    command.append(f"run.stop.max_real_attempts_per_agent={budget // 8}")
    command.append(f"grader.args.seed_index={seed_index}")
    command.append(f"grader.args.mode={mode}")
    return command


def main() -> int:
    if "--budget" not in sys.argv:
        raise SystemExit("v8 requires one explicit registered --budget per launch")
    previous = base.build_command
    base.build_command = build_command
    try:
        return base.main()
    finally:
        base.build_command = previous


if __name__ == "__main__":
    raise SystemExit(main())
