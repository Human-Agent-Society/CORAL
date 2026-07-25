#!/usr/bin/env python3
"""Audit the selected N=512 v4 threshold without pooling participant policies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from experiments.multi_island.isolation_audit import isolation_gate
from experiments.multi_island_hard import analyze_threshold_v2 as base
from experiments.multi_island_hard import run_threshold_v4 as runner

ROOT = Path(__file__).resolve().parent
DIAGNOSTICS = ROOT / "threshold_v4_diagnostics.json"
CONDITIONS = runner.CONDITIONS
BOUNDARY_EFFECT_FLOOR_Z = 0.25
MIGRATION_EFFECT_FLOOR_Z = 0.10
MAX_GLOBAL_FINAL_LINEAGES = 2
MIN_ACTIVE_LINEAGE_DIFFERENCE = 1.0
BEHAVIOR_METRICS = (
    "local_transition_rate",
    "structured_transition_rate",
    "restart_transition_rate",
    "operator_entropy",
    "local_coordinate_overlap",
    "inferred_cross_agent_adoption_rate",
    "final_inferred_lineages",
    "mean_active_inferred_lineages",
)


def selected_task_files(selection: dict[str, int]) -> dict[str, str]:
    k = selection["k"]
    return {
        runner.SMOOTH_TASK: "smooth512_replicated_v4.json",
        runner.RUGGED_TASKS[k]: f"rugged512_k{k}_replicated_v4.json",
    }


def configure(policy: str, selection: dict[str, int]) -> tuple[str, str]:
    task_files = selected_task_files(selection)
    smooth_task = runner.SMOOTH_TASK
    rugged_task = runner.RUGGED_TASKS[selection["k"]]
    base.BUDGETS = (selection["budget"],)
    base.MODEL_API_DOMAINS = runner.MODEL_API_DOMAINS
    base.heartbeat_for = runner.heartbeat_for
    base.migration_every = runner.migration_every
    base.DIAGNOSTICS = DIAGNOSTICS
    base.ROLE_FILE = runner.POLICY_ROLES[policy]
    base.TASK_FILES = task_files
    base.TASKS = tuple(task_files)
    base.SMOOTH_TASK = smooth_task
    base.RUGGED_TASK = rugged_task
    base.CONDITIONS = CONDITIONS
    base.INITIAL_SALT = "coral-threshold-v4"
    base.AGENT_TIMEOUT = 240
    base.PRACTICAL_DELTA_Z = BOUNDARY_EFFECT_FLOOR_Z
    base.CONTRAST_METRICS = (*base.CONTRAST_METRICS[:6], *BEHAVIOR_METRICS)
    return smooth_task, rugged_task


def post_migration_attempt_gate(run_dir: Path) -> tuple[bool, list[str]]:
    state = base.load_json(run_dir / ".coral/public/migration_state.json") or {}
    migrated = state.get("last_migrated_evals")
    if not isinstance(migrated, dict) or not migrated:
        return False, []
    records = base.real_records(run_dir)
    missing: list[str] = []
    for agent_id, boundary in migrated.items():
        try:
            sequence = int(boundary)
        except (TypeError, ValueError):
            missing.append(str(agent_id))
            continue
        if not any(
            index > sequence and str(record.get("agent_id")) == str(agent_id)
            for index, record in enumerate(records, start=1)
        ):
            missing.append(str(agent_id))
    return not missing, sorted(missing)


def decision(
    rows: list[dict[str, Any]],
    contrasts: list[dict[str, Any]],
    *,
    policy: str,
    budget: int,
    rugged_task: str,
    repetitions: int,
) -> dict[str, Any]:
    def contrast(task: str, name: str) -> dict[str, Any] | None:
        return next(
            (
                row
                for row in contrasts
                if row["task"] == task
                and int(row["budget"]) == budget
                and row["contrast"] == name
            ),
            None,
        )

    rugged_global = contrast(rugged_task, "multi_island_4_minus_global_8")
    rugged_partition = contrast(rugged_task, "multi_island_4_minus_partition_4")
    interaction = contrast("rugged_minus_smooth", "difference_in_multi_minus_global")
    global_rows = [
        row
        for row in rows
        if row["task"] == rugged_task
        and int(row["budget"]) == budget
        and row["condition"] == "global_8"
    ]
    multi_rows = [
        row
        for row in rows
        if row["task"] == rugged_task
        and int(row["budget"]) == budget
        and row["condition"] == "multi_island_4"
    ]
    ready = (
        repetitions == 8
        and len(global_rows) == 8
        and len(multi_rows) == 8
        and rugged_global is not None
        and rugged_partition is not None
        and interaction is not None
        and all(
            bool(row.get("confirmatory_ready"))
            and int(row.get("paired_repetitions", 0)) == 8
            for row in (rugged_global, rugged_partition, interaction)
        )
    )
    global_collapsed = bool(
        ready
        and all(
            int(row["final_inferred_lineages"]) <= MAX_GLOBAL_FINAL_LINEAGES
            for row in global_rows
        )
    )
    lineage_separation = bool(
        rugged_global is not None
        and float(rugged_global["mean_active_inferred_lineages_difference"])
        >= MIN_ACTIVE_LINEAGE_DIFFERENCE
        and float(rugged_global["mean_active_inferred_lineages_ci_low"]) > 0
    )
    manipulation_passes = ready and global_collapsed and lineage_separation
    boundary_score_passes = bool(
        rugged_global is not None
        and interaction is not None
        and float(rugged_global["random_z_difference"]) >= BOUNDARY_EFFECT_FLOOR_Z
        and float(rugged_global["random_z_ci_low"]) > 0
        and float(interaction["random_z_difference"]) >= BOUNDARY_EFFECT_FLOOR_Z
        and float(interaction["random_z_ci_low"]) > 0
    )
    migration_score_passes = bool(
        rugged_partition is not None
        and float(rugged_partition["random_z_difference"])
        >= MIGRATION_EFFECT_FLOOR_Z
        and float(rugged_partition["random_z_ci_low"]) > 0
    )
    boundary_supported = manipulation_passes and boundary_score_passes
    migration_supported = boundary_supported and migration_score_passes
    return {
        "policy": policy,
        "selected_budget": budget,
        "registered_repetitions": 8,
        "confirmatory_ready": ready,
        "maximum_global_final_lineages": MAX_GLOBAL_FINAL_LINEAGES,
        "minimum_active_lineage_difference": MIN_ACTIVE_LINEAGE_DIFFERENCE,
        "boundary_effect_floor_random_z": BOUNDARY_EFFECT_FLOOR_Z,
        "migration_effect_floor_random_z": MIGRATION_EFFECT_FLOOR_Z,
        "global_lineage_collapse_passes": global_collapsed,
        "active_lineage_separation_passes": lineage_separation,
        "manipulation_passes": manipulation_passes,
        "boundary_score_passes": boundary_score_passes,
        "migration_score_passes": migration_score_passes,
        "boundary_threshold_supported": boundary_supported,
        "migration_threshold_supported": migration_supported,
        "causal_policy_manipulation": policy == "high_diffusion",
        "interpretation": (
            "A boundary pass without a migration pass supports preserved lineages relative to "
            "global visibility, not selective migration relative to permanent partition."
        ),
    }


def parse_args(selection: dict[str, int], tasks: tuple[str, ...]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", choices=tuple(runner.POLICY_ROLES), required=True)
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--tasks", nargs="+", choices=tasks, default=list(tasks))
    parser.add_argument("--conditions", nargs="+", choices=CONDITIONS, default=list(CONDITIONS))
    parser.add_argument("--repetitions", type=int, default=8)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    args.budget = selection["budget"]
    return args


def main() -> int:
    try:
        selection = runner.registered_selection()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
    task_files = selected_task_files(selection)
    args = parse_args(selection, tuple(task_files))
    smooth_task, rugged_task = configure(args.policy, selection)
    if not DIAGNOSTICS.is_file():
        raise SystemExit("run diagnose_threshold_v4.py before analyzing participant cells")
    results_root = args.results_root or Path(
        f"/var/tmp/coral-institutions-results/nk-threshold-v4/{args.policy}"
    )
    output = args.output_dir or ROOT / f"threshold_v4_analysis_{args.policy}"
    references = base.diagnostics()
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    superseded: list[dict[str, Any]] = []
    expected = 0
    budget = selection["budget"]
    for task in args.tasks:
        for condition in args.conditions:
            for repetition in range(1, args.repetitions + 1):
                expected += 1
                base_run_dir = (
                    results_root.resolve()
                    / f"budget-{budget}"
                    / task
                    / condition
                    / f"rep-{repetition:02d}"
                )
                candidates = base.existing_run_dirs(base_run_dir)
                if not candidates:
                    failures.append(
                        {
                            "budget": budget,
                            "task": task,
                            "condition": condition,
                            "repetition": repetition,
                            "reasons": ["missing run"],
                        }
                    )
                    continue
                accepted_row: dict[str, Any] | None = None
                rejected: list[dict[str, Any]] = []
                for run_dir in candidates:
                    identity = base.load_json(run_dir / "operator-command.json")
                    if identity is None:
                        rejected.append({"run_dir": str(run_dir), "reasons": ["missing identity"]})
                        continue
                    row = base.collect(run_dir, identity, task, budget, references)
                    row["policy"] = args.policy
                    reasons = base.integrity(run_dir, identity, task, budget, row)
                    isolated, isolation_violations = isolation_gate(run_dir)
                    row["isolation_trace_gate"] = isolated
                    row["isolation_trace_violations"] = ";".join(isolation_violations)
                    if not isolated:
                        reasons.append("cross-island information access in runtime trace")
                    if condition == "multi_island_4":
                        post_migration, missing_agents = post_migration_attempt_gate(run_dir)
                        row["post_migration_attempt_gate"] = post_migration
                        row["migrants_without_later_attempt"] = ";".join(missing_agents)
                        if not post_migration:
                            reasons.append("migrant without a post-migration real attempt")
                    else:
                        row["post_migration_attempt_gate"] = True
                        row["migrants_without_later_attempt"] = ""
                    if reasons:
                        rejected.append(
                            {"run_dir": str(run_dir), "reasons": reasons, "observed": row}
                        )
                        continue
                    row["run_dir"] = str(run_dir)
                    row["superseded_run_count"] = len(rejected)
                    row["superseded_run_dirs"] = ";".join(
                        item["run_dir"] for item in rejected
                    )
                    accepted_row = row
                    superseded.extend(rejected)
                    break
                if accepted_row is None:
                    failures.append(
                        {
                            "budget": budget,
                            "task": task,
                            "condition": condition,
                            "repetition": repetition,
                            "reasons": ["no valid base or retry run"],
                            "candidate_runs": rejected,
                        }
                    )
                else:
                    rows.append(accepted_row)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    base.write_csv(output / "runs.csv", rows)
    contrasts, _legacy_threshold = base.make_contrasts(rows, args.repetitions)
    base.write_csv(output / "contrasts.csv", contrasts)
    result = decision(
        rows,
        contrasts,
        policy=args.policy,
        budget=budget,
        rugged_task=rugged_task,
        repetitions=args.repetitions,
    )
    result["smooth_task"] = smooth_task
    result["rugged_task"] = rugged_task
    (output / "threshold.json").write_text(json.dumps(result, indent=2) + "\n")
    audit = {
        "schema_version": 4,
        "policy": args.policy,
        "selected_k": selection["k"],
        "selected_budget": budget,
        "primary_metric": "final best random-baseline z-score",
        "boundary_contrast": "multi_island_4 minus global_8",
        "migration_contrast": "multi_island_4 minus partition_4",
        "accepted_rows": len(rows),
        "expected_rows": expected,
        "integrity_failures": failures,
        "superseded_invalid_runs": superseded,
    }
    (output / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(f"Audited {len(rows)}/{expected} threshold-v4 {args.policy} cells")
    if failures and not args.allow_incomplete:
        raise SystemExit(f"threshold-v4 matrix incomplete; see {output / 'audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
