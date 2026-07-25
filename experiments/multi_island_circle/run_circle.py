#!/usr/bin/env python3
"""Run the preregistered Circle Packing topology threshold study."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

from experiments.multi_island import run_matrix as base
from experiments.multi_island.isolation_audit import require_sandbox_contract

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
ROLE_FILE = ROOT / "eval_protocol.md"
TASK_NAME = "circle_packing"
CONDITIONS = ("global", "partition", "multi_island")
BUDGETS = (32, 64, 128)
MIGRATION_EVERY = 16
MODEL_API_DOMAINS = ("api.appintheloop.com",)
AGENT_TIMEOUT = 900
GRADER_TIMEOUT = 660
EVALUATION_TIMEOUT = 600

base.DEFAULT_RESULTS_ROOT = Path("/var/tmp/coral-institutions-results/circle-packing-v1")
base.TOPOLOGIES = {
    "global": {"count": 1, "migration": False},
    "partition": {"count": 2, "migration": False},
    "multi_island": {"count": 2, "migration": True},
}
base.TASKS = {
    TASK_NAME: base.TaskSpec(
        name=TASK_NAME,
        config=REPO_ROOT / "examples/math/circle_packing/task.yaml",
        cwd=REPO_ROOT,
        conditions=CONDITIONS,
    )
}

_BASE_BUILD_COMMAND = base.build_command
_BASE_ORDERED_CELLS = base.ordered_cells


def argument_values(flag: str) -> list[str] | None:
    if flag not in sys.argv:
        return None
    start = sys.argv.index(flag) + 1
    values: list[str] = []
    for value in sys.argv[start:]:
        if value.startswith("--"):
            break
        values.append(value)
    return values


def enforce_serial_launch() -> None:
    """Make the preregistered Latin-square order an actual serial order."""

    values = argument_values("--max-parallel")
    if values is None:
        sys.argv.extend(["--max-parallel", "1"])
    elif values != ["1"]:
        raise SystemExit("Circle Packing requires --max-parallel 1 for order balancing")


def heartbeat_for(budget: int) -> str:
    if budget not in BUDGETS:
        raise ValueError(f"unregistered Circle Packing budget: {budget}")
    return (
        '[{"name":"reflect","every":8},'
        '{"name":"consolidate","every":16,"is_global":true},'
        '{"name":"pivot","every":8,"trigger":"plateau"}]'
    )


def build_command(spec, condition: str, run_dir: Path) -> list[str]:
    command = _BASE_BUILD_COMMAND(spec, condition, run_dir)
    budget = base.EXPECTED_REAL_ATTEMPTS
    if budget not in BUDGETS:
        raise ValueError(f"unregistered Circle Packing budget: {budget}")
    if budget % 4:
        raise ValueError("Circle Packing budgets must divide evenly across four agents")
    for index, item in enumerate(command):
        if item.startswith("agents.runtime_options.role_file="):
            command[index] = f"agents.runtime_options.role_file={ROLE_FILE}"
        elif item.startswith("agents.sandbox.network="):
            command[index] = "agents.sandbox.network=allowlist"
        elif item.startswith("grader.parallel.max_workers="):
            command[index] = "grader.parallel.max_workers=2"
        elif item.startswith("islands.migration.every="):
            command[index] = f"islands.migration.every={MIGRATION_EVERY}"
        elif item.startswith("islands.migration.rank_window="):
            command[index] = f"islands.migration.rank_window={MIGRATION_EVERY}"
        elif item.startswith("islands.migration.remigration_cooldown="):
            command[index] = f"islands.migration.remigration_cooldown={MIGRATION_EVERY}"
    command.extend(
        (
            f"agents.heartbeat={heartbeat_for(budget)}",
            f"agents.timeout={AGENT_TIMEOUT}",
            f'agents.sandbox.allowed_domains=["{MODEL_API_DOMAINS[0]}"]',
            "islands.migration.dest_weighting=round_robin",
            f"run.stop.max_real_attempts_per_agent={budget // 4}",
            f"grader.timeout={GRADER_TIMEOUT}",
            f"grader.args.evaluation_timeout={EVALUATION_TIMEOUT}",
            "grader.args.harden_candidate=true",
        )
    )
    return command


def latin_square_cells(
    tasks: list[str],
    conditions: list[str] | None,
    repetitions: int,
) -> Iterator[tuple[base.TaskSpec, str, int]]:
    """Rotate condition order within each repetition block.

    Sequential smoke runs are vulnerable to model-service drift.  Rotation
    balances that order over three repetitions without changing assignment or
    selecting an order after outcomes are visible.
    """

    selected = set(conditions or CONDITIONS)
    for repetition in range(1, repetitions + 1):
        offset = (repetition - 1) % len(CONDITIONS)
        order = CONDITIONS[offset:] + CONDITIONS[:offset]
        for task_name in tasks:
            spec = base.TASKS[task_name]
            for condition in order:
                if condition in selected and condition in spec.conditions:
                    yield spec, condition, repetition


def main() -> int:
    try:
        require_sandbox_contract()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    enforce_serial_launch()
    if "--budget" not in sys.argv:
        raise SystemExit("Circle Packing requires one explicit registered --budget per launch")
    previous_build = base.build_command
    previous_order = base.ordered_cells
    base.build_command = build_command
    base.ordered_cells = latin_square_cells
    try:
        return base.main()
    finally:
        base.build_command = previous_build
        base.ordered_cells = previous_order


if __name__ == "__main__":
    raise SystemExit(main())
