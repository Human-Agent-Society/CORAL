#!/usr/bin/env python3
"""Run the harder v4 modular threshold matrix.

The v4 matrix adds a one-island/eight-agent control so that the primary
comparison can hold the total agent roster fixed:
``multi_island - partition`` measures migration, while
``multi_island - global_8`` measures fragmentation plus migration without an
agent-count change.
"""

from __future__ import annotations

import re
from pathlib import Path

from experiments.multi_island import run_matrix as base

ROOT = Path(__file__).resolve().parent
TASK_DIR = ROOT / "tasks/hard_active_modular_landscape_v4"
ROLE_FILE = ROOT / "hard_v4_eval_protocol.md"

base.DEFAULT_RESULTS_ROOT = Path("/var/tmp/coral-institutions-results/modular-hard-v4")
base.TOPOLOGIES["global_8"] = {"count": 1, "migration": False}
base.TASKS = {
    name: base.TaskSpec(
        name=name,
        config=TASK_DIR / config,
        cwd=TASK_DIR,
        conditions=("global", "global_8", "partition", "multi_island"),
    )
    for name, config in {
        "smooth_hard_v4": "task_smooth_v4.yaml",
        "rugged_hard_v4": "task_rugged_v4.yaml",
    }.items()
}

_BASE_BUILD_COMMAND = base.build_command


def repetition_seed_index(run_dir: Path) -> int:
    match = re.search(r"rep-(\d+)", run_dir.name)
    if match is None:
        raise ValueError(f"run directory has no repetition index: {run_dir}")
    return int(match.group(1)) - 1


def build_command(spec, condition, run_dir):
    """Use the v4 role, paired seed, and budget-scaled migration cadence."""
    command = _BASE_BUILD_COMMAND(spec, condition, run_dir)
    budget = base.EXPECTED_REAL_ATTEMPTS
    every = max(16, min(64, budget // 8))
    seed_index = repetition_seed_index(run_dir)
    for index, item in enumerate(command):
        if item.startswith("agents.runtime_options.role_file="):
            command[index] = f"agents.runtime_options.role_file={ROLE_FILE}"
        elif item.startswith("islands.migration.every="):
            command[index] = f"islands.migration.every={every}"
        elif item.startswith("islands.migration.rank_window="):
            command[index] = f"islands.migration.rank_window={every}"
        elif item.startswith("islands.migration.remigration_cooldown="):
            command[index] = "islands.migration.remigration_cooldown=16"
        elif condition == "global_8" and item == "agents.count=4":
            command[index] = "agents.count=8"
    command.append(f"grader.args.seed_index={seed_index}")
    mode = "smooth" if spec.name.startswith("smooth_") else "rugged"
    command.append(f"grader.args.mode={mode}")
    return command


base.build_command = build_command


if __name__ == "__main__":
    raise SystemExit(base.main())
