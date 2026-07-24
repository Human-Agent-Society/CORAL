#!/usr/bin/env python3
"""Run the v5 high-dimensional modular threshold matrix."""

from __future__ import annotations

import re
from pathlib import Path

from experiments.multi_island import run_matrix as base

ROOT = Path(__file__).resolve().parent
TASK_DIR = ROOT / "tasks/hard_active_modular_landscape_v5"
ROLE_FILE = ROOT / "hard_v5_eval_protocol.md"

base.DEFAULT_RESULTS_ROOT = Path("/var/tmp/coral-institutions-results/modular-hard-v5")
base.TOPOLOGIES["global_8"] = {"count": 1, "migration": False}
base.TASKS = {
    name: base.TaskSpec(
        name=name,
        config=TASK_DIR / config,
        cwd=TASK_DIR,
        conditions=("global", "global_8", "partition", "multi_island"),
    )
    for name, config in {
        "smooth_hard_v5": "task_smooth_v5.yaml",
        "rugged_hard_v5": "task_rugged_v5.yaml",
    }.items()
}

_BASE_BUILD_COMMAND = base.build_command


def migration_every(budget: int) -> int:
    """Return the pre-registered budget-scaled migration cadence."""
    return max(64, min(256, budget // 4))


def repetition_seed_index(run_dir: Path) -> int:
    match = re.search(r"rep-(\d+)", run_dir.name)
    if match is None:
        raise ValueError(f"run directory has no repetition index: {run_dir}")
    return int(match.group(1)) - 1


def build_command(spec, condition, run_dir):
    """Use the v5 role, paired seed, and budget-scaled migration cadence."""
    command = _BASE_BUILD_COMMAND(spec, condition, run_dir)
    budget = base.EXPECTED_REAL_ATTEMPTS
    # Let an agent spend enough evaluations to make meaningful progress on a
    # module before moving it.  The smooth coordinate/provenance anchor is 34
    # evaluations per module; a 128-evaluation minimum at B=512 avoids
    # measuring repeated startup/reorientation instead of transfer.  Rugged
    # enumeration uses the same pre-registered cadence and caps it at 256 so
    # large-budget cells still receive several migration opportunities.
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
            command[index] = "islands.migration.remigration_cooldown=64"
        elif item.startswith("grader.parallel.max_workers="):
            command[index] = "grader.parallel.max_workers=4"
        elif condition in {"global_8", "partition", "multi_island"} and item == "agents.count=4":
            command[index] = "agents.count=8"
    command.append(f"grader.args.seed_index={seed_index}")
    mode = "smooth" if spec.name.startswith("smooth_") else "rugged"
    command.append(f"grader.args.mode={mode}")
    return command


base.build_command = build_command


if __name__ == "__main__":
    raise SystemExit(base.main())
