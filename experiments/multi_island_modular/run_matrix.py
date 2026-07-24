#!/usr/bin/env python3
"""Run the modular multi-island matrix with isolated budget slices."""

from __future__ import annotations

from pathlib import Path

from experiments.multi_island import run_matrix as base

ROOT = Path(__file__).resolve().parent
TASK_DIR = ROOT / "tasks/modular_landscape"
ACTIVE_TASK_DIR = ROOT / "tasks/active_modular_landscape"
ROLE_FILE = ROOT / "eval_protocol.md"

base.DEFAULT_RESULTS_ROOT = Path("/var/tmp/coral-institutions-results/modular-v1")
base.EXPECTED_REAL_ATTEMPTS = 128
base.TASKS = {
    **{
        name: base.TaskSpec(
            name=name,
            config=TASK_DIR / config,
            cwd=TASK_DIR,
            conditions=("global", "partition", "multi_island"),
        )
        for name, config in {
            "smooth_modular128": "task_smooth_modular128.yaml",
            "rugged_modular128": "task_rugged_modular128.yaml",
            "smooth_modular192": "task_smooth_modular192.yaml",
            "rugged_modular192": "task_rugged_modular192.yaml",
        }.items()
    },
    **{
        name: base.TaskSpec(
            name=name,
            config=ACTIVE_TASK_DIR / config,
            cwd=ACTIVE_TASK_DIR,
            conditions=("global", "partition", "multi_island"),
        )
        for name, config in {
            "smooth_active128": "task_smooth_active128.yaml",
            "rugged_active128": "task_rugged_active128.yaml",
        }.items()
    },
}

_BASE_BUILD_COMMAND = base.build_command


def build_command(spec, condition, run_dir):
    """Use the modular role and scale migration cadence with the budget."""
    command = _BASE_BUILD_COMMAND(spec, condition, run_dir)
    for index, item in enumerate(command):
        if item.startswith("agents.runtime_options.role_file="):
            command[index] = f"agents.runtime_options.role_file={ROLE_FILE}"
        elif item.startswith("islands.migration.every="):
            every = max(8, base.EXPECTED_REAL_ATTEMPTS // 4)
            command[index] = f"islands.migration.every={every}"
        elif item.startswith("islands.migration.rank_window="):
            every = max(8, base.EXPECTED_REAL_ATTEMPTS // 4)
            command[index] = f"islands.migration.rank_window={every}"
        elif item.startswith("islands.migration.remigration_cooldown="):
            command[index] = "islands.migration.remigration_cooldown=8"
    return command


base.build_command = build_command


if __name__ == "__main__":
    raise SystemExit(base.main())
