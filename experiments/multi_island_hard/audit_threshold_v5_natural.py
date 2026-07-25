#!/usr/bin/env python3
"""Fail-closed integrity audit for the v5 natural-agent topology arm."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from experiments.multi_island.isolation_audit import isolation_gate
from experiments.multi_island_hard import analyze_threshold_v2 as base
from experiments.multi_island_hard import analyze_threshold_v5_mechanism as metrics
from experiments.multi_island_hard import audit_threshold_v4_canary as common
from experiments.multi_island_hard import run_threshold_v5_natural as runner
from experiments.multi_island_hard.behavior_metrics import behavior_metrics

TASKDATA = runner.mechanism.TASK_DIR / "taskdata"
TASK_FILES = {
    runner.mechanism.SMOOTH_TASK: ("smooth512_permuted_leading_ones_replicated_v5.json"),
    runner.mechanism.RUGGED_TASKS[64]: "rugged512_k64_replicated_v5.json",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=runner.RESULTS_ROOT)
    parser.add_argument("--repetitions", type=int, default=8)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def configuration_errors(
    run_dir: Path,
    identity: dict[str, Any],
    *,
    task: str,
    condition: str,
    repetition: int,
    budget: int,
) -> list[str]:
    errors: list[str] = []
    values = base.overrides(identity)
    topology = runner.TOPOLOGIES[condition]
    every = budget // 4
    expected = {
        "agents.count": "8",
        "agents.runtime": "opencode",
        "agents.model": "mafia/glm-5.2",
        "agents.research": "false",
        "agents.timeout": str(runner.AGENT_TIMEOUT),
        "agents.runtime_options.role_file": str(runner.ROLE_FILE),
        "agents.sandbox.enabled": "true",
        "agents.sandbox.provider": "srt",
        "agents.sandbox.network": "allowlist",
        "agents.sandbox.allowed_domains": '["api.appintheloop.com"]',
        "grader.parallel.max_workers": str(runner.GRADER_WORKERS),
        "grader.args.disable_tune": "true",
        "grader.args.seed_index": str(repetition - 1),
        "islands.count": str(topology["count"]),
        "islands.migration.enabled": str(topology["migration"]).lower(),
        "islands.migration.every": str(every),
        "islands.migration.rank_window": str(every),
        "islands.migration.min_evals": "1",
        "islands.migration.max_per_cycle": str(topology["max_per_cycle"]),
        "islands.migration.remigration_cooldown": str(every),
        "islands.migration.dest_weighting": "round_robin",
        "run.stop.max_real_attempts": str(budget),
        "run.stop.max_real_attempts_per_agent": str(budget // 8),
        "run.session": "local",
        "agents.heartbeat": runner.heartbeat_for(budget),
    }
    for key, expected_value in expected.items():
        if values.get(key) != expected_value:
            errors.append(f"{key}={values.get(key)!r}, expected {expected_value!r}")
    if "agents.runtime_options.command" in values:
        errors.append("natural-agent cell contains a scripted runtime command")
    if identity.get("task") != task or identity.get("condition") != condition:
        errors.append("operator identity disagrees with matrix cell")
    if int(identity.get("repetition", -1)) != repetition:
        errors.append("operator repetition disagrees with matrix cell")
    try:
        resolved = yaml.safe_load((run_dir / ".coral/config.yaml").read_text())
        domains = resolved["agents"]["sandbox"].get("allowed_domains", [])
    except (OSError, TypeError, KeyError, yaml.YAMLError):
        errors.append("resolved config is unreadable")
    else:
        if domains != list(runner.MODEL_API_DOMAINS):
            errors.append(f"network allowlist={domains!r}, expected model API only")
    frozen = TASKDATA / TASK_FILES[task]
    private = run_dir / ".coral/private" / TASK_FILES[task]
    if not private.is_file() or private.read_bytes() != frozen.read_bytes():
        errors.append("private held-out landscape bundle mismatch")
    return errors


def attempt_timestamp(record: dict[str, Any]) -> float | None:
    try:
        return datetime.fromisoformat(str(record["timestamp"])).timestamp()
    except (KeyError, TypeError, ValueError):
        return None


def migration_errors(
    run_dir: Path,
    condition: str,
    records: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> tuple[list[str], int, int]:
    errors: list[str] = []
    migrations = [event for event in events if event.get("source") == "migration"]
    notes = list(run_dir.glob(".coral/islands/*/notes/migrations/migration_*.md"))
    if condition != "multi_island_4":
        if migrations:
            errors.append(f"control contains {len(migrations)} migration restarts")
        if notes:
            errors.append("control contains migration notes")
        return errors, len(migrations), 0
    if not migrations:
        errors.append("multi-island treatment has no realized migration")
        return errors, 0, 0

    migrated_destinations: set[str] = set()
    exposed_destinations: set[str] = set()
    exposed_events = 0
    for event in migrations:
        destination = str(event.get("log_island", ""))
        if destination:
            migrated_destinations.add(destination)
        try:
            boundary = datetime.fromisoformat(str(event["timestamp"])).timestamp()
        except (KeyError, TypeError, ValueError):
            errors.append(f"{event.get('agent_id', '')}: invalid migration timestamp")
            continue
        migrant = common.base_agent_id(str(event.get("agent_id", "")))
        later = any(
            common.base_agent_id(str(record.get("agent_id", ""))) == migrant
            and record.get("metadata", {}).get("island_id") == destination
            and (timestamp := attempt_timestamp(record)) is not None
            and timestamp > boundary
            for record in records
        )
        if later:
            exposed_events += 1
            exposed_destinations.add(destination)
    unexposed = sorted(migrated_destinations - exposed_destinations)
    if unexposed:
        errors.append(f"no post-migration migrant submission in destinations={unexposed}")
    return errors, len(migrations), exposed_events


def collect(
    run_dir: Path,
    *,
    task: str,
    condition: str,
    repetition: int,
    budget: int,
) -> dict[str, Any]:
    identity = base.load_json(run_dir / "operator-command.json")
    errors = (
        ["missing operator identity"]
        if identity is None
        else configuration_errors(
            run_dir,
            identity,
            task=task,
            condition=condition,
            repetition=repetition,
            budget=budget,
        )
    )
    records = base.real_records(run_dir)
    if len(records) != budget:
        errors.append(f"real attempts={len(records)}, expected {budget}")
    if base.disallowed_records(run_dir):
        errors.append("disallowed tune or grader-error attempt present")
    if any(not isinstance(record.get("score"), (int, float)) for record in records):
        errors.append("non-numeric real score present")
    stop = base.load_json(run_dir / ".coral/public/auto_stop.json") or {}
    if stop.get("reason") != "max_real_attempts":
        errors.append(f"auto-stop reason={stop.get('reason')!r}")

    counts = Counter(common.base_agent_id(str(record.get("agent_id", ""))) for record in records)
    if len(counts) != 8 or set(counts.values()) != {budget // 8}:
        errors.append(f"unbalanced base-agent quotas: {dict(sorted(counts.items()))}")

    candidates: dict[str, str] = {}
    try:
        candidates = common.source_candidates(
            run_dir,
            {str(record["commit_hash"]) for record in records},
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        errors.append(str(exc))
    first_by_agent: dict[str, str] = {}
    parsed: list[tuple[dict[str, Any], str]] = []
    scores: list[float] = []
    progress: list[float] = []
    best = float("-inf")
    for record in records:
        commit = str(record.get("commit_hash", ""))
        candidate = candidates.get(commit)
        if candidate is not None:
            parsed.append((record, candidate))
            agent = common.base_agent_id(str(record.get("agent_id", "")))
            first_by_agent.setdefault(agent, candidate)
        score = record.get("score")
        if isinstance(score, (int, float)):
            best = max(best, float(score))
            scores.append(float(score))
            progress.append(best)
    initial_errors = sorted(
        agent
        for agent, candidate in first_by_agent.items()
        if candidate != common.expected_initial(agent)
    )
    if len(first_by_agent) != 8 or initial_errors:
        errors.append(
            f"topology-invariant initial candidate failed: agents={len(first_by_agent)}, "
            f"mismatches={initial_errors}"
        )

    events = common.prompt_events(run_dir)
    migration_failures, migration_events, exposed_events = migration_errors(
        run_dir,
        condition,
        records,
        events,
    )
    errors.extend(migration_failures)
    isolated, violations = isolation_gate(run_dir)
    if not isolated:
        errors.extend(f"isolation: {violation}" for violation in violations)

    candidates_in_order = [candidate for _record, candidate in parsed]
    unique_candidates = len(set(candidates_in_order))
    row: dict[str, Any] = {
        "run_dir": str(run_dir),
        "task": task,
        "condition": condition,
        "repetition": repetition,
        "budget": budget,
        "valid": not errors,
        "errors": errors,
        "real_attempts": len(records),
        "base_agent_attempts": dict(sorted(counts.items())),
        "final_best": max(scores) if scores else None,
        "best_so_far_auc": statistics.fmean(progress) if progress else None,
        "midpoint_diversity": metrics.diversity_at(
            records,
            candidates,
            min(budget // 2, len(records)),
        )
        if len(candidates) == len(records)
        else None,
        "final_diversity": metrics.diversity_at(records, candidates, len(records))
        if len(candidates) == len(records)
        else None,
        "unique_candidates": unique_candidates,
        "duplicate_candidate_rate": (
            (len(candidates_in_order) - unique_candidates) / len(candidates_in_order)
            if candidates_in_order
            else None
        ),
        "migration_events": migration_events,
        "post_migration_migrant_submission_events": exposed_events,
        "isolation_trace_gate": isolated,
        "isolation_trace_violations": violations,
    }
    row.update(behavior_metrics(parsed))
    return row


def main() -> int:
    args = parse_args()
    selection = runner.mechanism.registered_selection()
    budget = selection["budget"]
    if args.repetitions not in range(1, 9):
        raise SystemExit("repetitions must be in 1..8")
    tasks = (
        runner.mechanism.SMOOTH_TASK,
        runner.mechanism.RUGGED_TASKS[selection["k"]],
    )
    budget_root = args.results_root.resolve() / f"budget-{budget}"
    cells: list[dict[str, Any]] = []
    for repetition in range(1, args.repetitions + 1):
        for task in tasks:
            for condition in runner.CONDITIONS:
                base_dir = budget_root / task / condition / f"rep-{repetition:02d}"
                candidates = base.existing_run_dirs(base_dir)
                if not candidates:
                    cells.append(
                        {
                            "run_dir": str(base_dir),
                            "task": task,
                            "condition": condition,
                            "repetition": repetition,
                            "valid": False,
                            "errors": ["missing run"],
                        }
                    )
                    continue
                rejected: list[dict[str, Any]] = []
                accepted: dict[str, Any] | None = None
                for run_dir in candidates:
                    cell = collect(
                        run_dir,
                        task=task,
                        condition=condition,
                        repetition=repetition,
                        budget=budget,
                    )
                    if cell["valid"]:
                        accepted = cell
                        break
                    rejected.append(cell)
                cell = accepted or rejected[-1]
                cell["superseded_invalid_runs"] = [
                    row["run_dir"] for row in (rejected if accepted else rejected[:-1])
                ]
                cells.append(cell)
    expected = len(tasks) * len(runner.CONDITIONS) * args.repetitions
    valid = sum(bool(cell.get("valid")) for cell in cells)
    rosters = {
        tuple(sorted(str(agent) for agent in cell.get("base_agent_attempts", {})))
        for cell in cells
        if cell.get("valid")
    }
    matrix_errors = (
        []
        if len(rosters) == 1
        else [f"base-agent roster differs across paired cells: {sorted(rosters)}"]
    )
    result = {
        "schema_version": 1,
        "scope": "held-out v5 natural-agent topology integrity audit",
        "budget": budget,
        "repetitions": args.repetitions,
        "valid_cells": valid,
        "expected_cells": expected,
        "matrix_errors": matrix_errors,
        "cells": cells,
        "interpretation": (
            "Natural-agent results are separate from the scripted mechanism arm; "
            "passing integrity does not by itself establish a topology effect."
        ),
    }
    output = args.output or budget_root / "natural-agent-audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"Audited {valid}/{expected} v5 natural-agent cells")
    if valid != expected or matrix_errors:
        raise SystemExit(f"v5 natural-agent matrix invalid; see {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
