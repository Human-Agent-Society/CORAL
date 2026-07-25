#!/usr/bin/env python3
"""Run the registered natural-agent arm at the v5 hard Smooth/Rugged anchor."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from coral.config import CoralConfig
from experiments.multi_island import run_matrix as base
from experiments.multi_island.isolation_audit import require_sandbox_contract
from experiments.multi_island_hard import run_threshold_v4 as v4
from experiments.multi_island_hard import run_threshold_v5_mechanism as mechanism

ROOT = Path(__file__).resolve().parent
ROLE_FILE = ROOT / "threshold_v5_natural_protocol.md"
RESULTS_ROOT = Path("/var/tmp/coral-institutions-results/nk-threshold-v5-mechanism-v2/natural")
MODEL_API_DOMAINS = ("api.appintheloop.com",)
AGENT_TIMEOUT = 240
GRADER_WORKERS = 4
CONDITIONS = mechanism.CONDITIONS
TASKS = mechanism.TASKS
TOPOLOGIES = mechanism.TOPOLOGIES
BASE_BUILD_COMMAND = mechanism.BASE_BUILD_COMMAND
BASE_ORDERED_CELLS = base.ordered_cells


def heartbeat_for(budget: int) -> str:
    every = max(128, budget // 8)
    return json.dumps(
        [
            {"name": "reflect", "every": every},
            {"name": "consolidate", "every": every * 2, "is_global": True},
            {"name": "pivot", "every": every, "trigger": "plateau"},
        ],
        separators=(",", ":"),
    )


def seed_contract_errors() -> list[str]:
    errors: list[str] = []
    for task, filename in mechanism.CONFIGS.items():
        try:
            config = CoralConfig.from_yaml(mechanism.TASK_DIR / filename)
        except (OSError, TypeError, ValueError) as exc:
            errors.append(f"{task}: unreadable config: {exc}")
            continue
        if config.workspace.seed_path is not None:
            errors.append(f"{task}: workspace.seed_path must be null")
        source = Path(config.workspace.repo_path)
        if not source.is_absolute():
            source = (mechanism.TASK_DIR / source).resolve()
        try:
            candidate = v4._literal_candidate(source / "candidate.py")
        except (OSError, SyntaxError, ValueError) as exc:
            errors.append(f"{task}: invalid source candidate: {exc}")
        else:
            if len(candidate) != 512 or set(candidate) - {"0", "1"}:
                errors.append(f"{task}: source candidate is not a 512-bit literal")
        if not (source / "initialize_candidate.py").is_file():
            errors.append(f"{task}: initialize_candidate.py is missing")
    return errors


def build_command(spec: Any, condition: str, run_dir: Path) -> list[str]:
    command = BASE_BUILD_COMMAND(spec, condition, run_dir, topologies=TOPOLOGIES)
    budget = base.EXPECTED_REAL_ATTEMPTS
    selection = mechanism.registered_selection()
    if budget != selection["budget"]:
        raise ValueError("natural v5 arm requires the registered budget")
    if budget % 8:
        raise ValueError("natural v5 budget must divide evenly across eight agents")
    every = budget // 4
    topology = TOPOLOGIES[condition]
    replacements = {
        "agents.count=": "agents.count=8",
        "agents.runtime_options.role_file=": (f"agents.runtime_options.role_file={ROLE_FILE}"),
        "agents.timeout=": f"agents.timeout={AGENT_TIMEOUT}",
        "agents.sandbox.network=": "agents.sandbox.network=allowlist",
        "grader.parallel.max_workers=": (f"grader.parallel.max_workers={GRADER_WORKERS}"),
        "islands.migration.every=": f"islands.migration.every={every}",
        "islands.migration.rank_window=": f"islands.migration.rank_window={every}",
        "islands.migration.remigration_cooldown=": (
            f"islands.migration.remigration_cooldown={every}"
        ),
        "islands.migration.max_per_cycle=": (
            f"islands.migration.max_per_cycle={topology['max_per_cycle']}"
        ),
    }
    for prefix, replacement in replacements.items():
        mechanism.replace_override(command, prefix, replacement)
    command.extend(
        [
            f"agents.heartbeat={heartbeat_for(budget)}",
            'agents.sandbox.allowed_domains=["api.appintheloop.com"]',
            "islands.migration.dest_weighting=round_robin",
            f"run.stop.max_real_attempts_per_agent={budget // 8}",
            f"grader.args.seed_index={v4.repetition_seed_index(run_dir)}",
        ]
    )
    return command


def enforce_matrix(selection: dict[str, int]) -> None:
    budget_values = v4._argument_values("--budget")
    if budget_values != [str(selection["budget"])]:
        raise SystemExit(f"v5 natural arm requires explicit --budget {selection['budget']}")
    allowed = (mechanism.SMOOTH_TASK, mechanism.RUGGED_TASKS[selection["k"]])
    requested = v4._argument_values("--tasks")
    if requested is None:
        sys.argv.extend(["--tasks", *allowed])
    elif not requested or any(task not in allowed for task in requested):
        raise SystemExit(f"v5 natural arm permits only: {' '.join(allowed)}")
    conditions = v4._argument_values("--conditions")
    if conditions is None:
        sys.argv.extend(["--conditions", *CONDITIONS])
    elif tuple(conditions) != CONDITIONS:
        raise SystemExit("v5 natural arm requires global, partition, and multi-island")
    parallel = v4._argument_values("--max-parallel")
    if parallel is None:
        sys.argv.extend(["--max-parallel", "2"])
    elif parallel != ["2"]:
        raise SystemExit("v5 natural arm requires --max-parallel 2 for paired task blocks")


def latin_square_cells(
    tasks: list[str],
    conditions: list[str] | None,
    repetitions: int,
) -> Iterator[tuple[base.TaskSpec, str, int]]:
    """Rotate condition stages while launching the paired tasks together."""

    selected = set(conditions or CONDITIONS)
    for repetition in range(1, repetitions + 1):
        offset = (repetition - 1) % len(CONDITIONS)
        order = CONDITIONS[offset:] + CONDITIONS[:offset]
        for condition in order:
            for task_name in tasks:
                spec = TASKS[task_name]
                if condition in selected and condition in spec.conditions:
                    yield spec, condition, repetition


def main() -> int:
    try:
        require_sandbox_contract()
        errors = seed_contract_errors()
        if errors:
            raise RuntimeError("; ".join(errors))
        selection = mechanism.registered_selection()
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
    enforce_matrix(selection)
    previous = (
        base.TASKS,
        base.TOPOLOGIES,
        base.DEFAULT_RESULTS_ROOT,
        base.build_command,
        base.ordered_cells,
        base.EXPECTED_REAL_ATTEMPTS,
    )
    base.TASKS = TASKS
    base.TOPOLOGIES = TOPOLOGIES
    base.DEFAULT_RESULTS_ROOT = RESULTS_ROOT
    base.build_command = build_command
    base.ordered_cells = latin_square_cells
    try:
        return base.main()
    finally:
        (
            base.TASKS,
            base.TOPOLOGIES,
            base.DEFAULT_RESULTS_ROOT,
            base.build_command,
            base.ordered_cells,
            base.EXPECTED_REAL_ATTEMPTS,
        ) = previous


if __name__ == "__main__":
    raise SystemExit(main())
