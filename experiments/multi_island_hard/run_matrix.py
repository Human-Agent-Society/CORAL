#!/usr/bin/env python3
"""Run the high-dimensional NK difficulty ladder with glm-5.2 agents.

The process/sandbox/manifest machinery is shared with the authoritative
experiment. This wrapper only replaces the task registry and raises the fixed
real budget from 16 to 24 evaluations per cell.
"""

from __future__ import annotations

from pathlib import Path

from experiments.multi_island import run_matrix as base

REPO_ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = Path(__file__).resolve().parent / "tasks/institutional_landscape"
ROLE_FILE = Path(__file__).resolve().parent / "eval_protocol.md"

base.DEFAULT_RESULTS_ROOT = Path("/var/tmp/coral-institutions-results/hard-ladder-v1")
base.EXPECTED_REAL_ATTEMPTS = 24
base.TASKS = {
    name: base.TaskSpec(
        name=name,
        config=TASK_DIR / config,
        cwd=TASK_DIR,
        conditions=("global", "partition", "multi_island"),
    )
    for name, config in {
        "smooth128": "task_smooth128.yaml",
        "rugged128_k4": "task_rugged128_k4.yaml",
        "rugged128_k12": "task_rugged128_k12.yaml",
        "rugged128_k24": "task_rugged128_k24.yaml",
    }.items()
}


_BASE_BUILD_COMMAND = base.build_command


def build_command(spec, condition, run_dir):
    """Use the ladder protocol and scale migration cadence with the budget."""
    command = _BASE_BUILD_COMMAND(spec, condition, run_dir)
    prefix = "agents.runtime_options.role_file="
    for index, item in enumerate(command):
        if item.startswith(prefix):
            command[index] = f"{prefix}{ROLE_FILE}"
            break
    every = max(6, base.EXPECTED_REAL_ATTEMPTS // 4)
    cooldown = 6
    for index, item in enumerate(command):
        if item.startswith("islands.migration.every="):
            command[index] = f"islands.migration.every={every}"
        elif item.startswith("islands.migration.rank_window="):
            command[index] = f"islands.migration.rank_window={every}"
        elif item.startswith("islands.migration.remigration_cooldown="):
            command[index] = f"islands.migration.remigration_cooldown={cooldown}"
    return command


base.build_command = build_command


if __name__ == "__main__":
    raise SystemExit(base.main())
