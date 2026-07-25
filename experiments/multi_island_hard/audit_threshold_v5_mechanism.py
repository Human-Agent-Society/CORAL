#!/usr/bin/env python3
"""Fail-closed integrity audit for the hard-Smooth/Rugged mechanism arm."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import analyze_threshold_v2 as base
from experiments.multi_island_hard import audit_threshold_v4_canary as common
from experiments.multi_island_hard import run_threshold_v5_mechanism as runner


def require_budget_not_invalidated(budget_root: Path) -> None:
    """Reject a whole budget slice that has been explicitly invalidated."""
    marker = budget_root / "experiment-invalid.json"
    if marker.is_file():
        raise SystemExit(
            f"budget root is invalidated by {marker}; use a fresh results root"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=runner.RESULTS_ROOT)
    parser.add_argument("--budget", type=int, default=runner.registered_selection()["budget"])
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.budget < 32 or args.budget % 8 or args.repetitions not in range(1, 9):
        raise SystemExit("budget must be >=32 and divisible by 8; repetitions must be 1..8")
    selection = runner.registered_selection()
    tasks = (runner.SMOOTH_TASK, runner.RUGGED_TASKS[selection["k"]])
    root = args.results_root.resolve()
    budget_root = root if root.name == f"budget-{args.budget}" else root / f"budget-{args.budget}"
    require_budget_not_invalidated(budget_root)
    attempts_per_agent = args.budget // 8
    migration_every = args.budget // 4
    cells: list[dict[str, Any]] = []
    schedules: defaultdict[tuple[str, int], set[tuple[int, ...]]] = defaultdict(set)
    initial_hashes: defaultdict[str, set[str]] = defaultdict(set)
    schedule_coverage: defaultdict[tuple[str, int], int] = defaultdict(int)
    initial_coverage: defaultdict[str, int] = defaultdict(int)
    rosters: set[tuple[str, ...]] = set()
    for repetition in range(1, args.repetitions + 1):
        for task in tasks:
            for condition in runner.CONDITIONS:
                base_run_dir = budget_root / task / condition / f"rep-{repetition:02d}"
                candidates = base.existing_run_dirs(base_run_dir)
                if not candidates:
                    cells.append(
                        {
                            "run_dir": str(base_run_dir),
                            "task": task,
                            "condition": condition,
                            "repetition": repetition,
                            "valid": False,
                            "errors": ["missing run"],
                        }
                    )
                    continue
                accepted: dict[str, Any] | None = None
                rejected: list[dict[str, Any]] = []
                for run_dir in candidates:
                    cell = common.audit_run(
                        run_dir,
                        condition,
                        budget=args.budget,
                        attempts_per_agent=attempts_per_agent,
                        migration_every=migration_every,
                        grader_workers=8,
                        seed_index=repetition - 1,
                    )
                    cell.update({"task": task, "repetition": repetition})
                    if cell["valid"]:
                        accepted = cell
                        break
                    rejected.append(cell)
                cell = accepted or rejected[-1]
                cell["superseded_invalid_runs"] = [
                    row["run_dir"] for row in (rejected if accepted else rejected[:-1])
                ]
                if cell["valid"]:
                    roster = tuple(
                        sorted(
                            {
                                common.base_agent_id(str(trace["agent_id"]))
                                for trace in cell["traces"]
                            }
                        )
                    )
                    rosters.add(roster)
                    for trace in cell["traces"]:
                        agent = common.base_agent_id(str(trace["agent_id"]))
                        if trace["type"] == "initial":
                            initial_hashes[agent].add(str(trace["candidate_sha256"]))
                            initial_coverage[agent] += 1
                        else:
                            key = (agent, int(trace["local_attempt"]))
                            schedules[key].add(
                                tuple(int(index) for index in trace["flips"])
                            )
                            schedule_coverage[key] += 1
                cell.pop("traces", None)
                cells.append(cell)

    expected_cells = len(tasks) * len(runner.CONDITIONS) * args.repetitions
    matrix_errors = [
        f"mutation schedule differs across paired cells for {key}"
        for key, variants in sorted(schedules.items())
        if len(variants) != 1
    ]
    matrix_errors.extend(
        f"initial candidate differs across paired cells for {agent}"
        for agent, variants in sorted(initial_hashes.items())
        if len(variants) != 1
    )
    if len(rosters) != 1:
        matrix_errors.append(
            f"base-agent roster differs across paired cells: {sorted(rosters)}"
        )
    matrix_errors.extend(
        f"initial candidate coverage for {agent} is {count}, expected {expected_cells}"
        for agent, count in sorted(initial_coverage.items())
        if count != expected_cells
    )
    matrix_errors.extend(
        f"mutation schedule coverage for {key} is {count}, expected {expected_cells}"
        for key, count in sorted(schedule_coverage.items())
        if count != expected_cells
    )
    valid_cells = sum(bool(cell.get("valid")) for cell in cells)
    registered = bool(
        args.budget in runner.CONFIRMATORY_BUDGETS
        and "engineering-smoke" not in budget_root.parts
    )
    audit = {
        "schema_version": 1,
        "scope": "held-out scripted topology mechanism integrity audit",
        "budget": args.budget,
        "registered_budget": registered,
        "repetitions": args.repetitions,
        "valid_cells": valid_cells,
        "expected_cells": expected_cells,
        "matrix_errors": matrix_errors,
        "cells": cells,
        "interpretation": (
            "Passing establishes treatment fidelity. Performance is analyzed separately; "
            "even a registered scripted effect is topology-mechanism evidence only."
        ),
    }
    output = args.output or budget_root / "scripted-mechanism-audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(f"Audited {valid_cells}/{expected_cells} scripted mechanism cells")
    if valid_cells != expected_cells or matrix_errors:
        raise SystemExit(f"scripted mechanism matrix invalid; see {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
