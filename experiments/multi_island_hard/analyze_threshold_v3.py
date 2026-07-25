#!/usr/bin/env python3
"""Audit N=256 natural or high-diffusion threshold cells without pooling them."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import analyze_threshold_v2 as base
from experiments.multi_island_hard import run_threshold_v3 as runner

ROOT = Path(__file__).resolve().parent
DIAGNOSTICS = ROOT / "threshold_v3_diagnostics.json"
TASK_FILES = {
    "smooth256_rep_v3": "smooth256_replicated_v3.json",
    "rugged256_k32_rep_v3": "rugged256_k32_replicated_v3.json",
}
TASKS = tuple(TASK_FILES)
SMOOTH_TASK = "smooth256_rep_v3"
RUGGED_TASK = "rugged256_k32_rep_v3"
CONDITIONS = ("global_8", "partition_4", "multi_island_2", "multi_island_4")
PRACTICAL_DELTA_Z = 0.50
MIN_HIGH_DIFFUSION_ADOPTION = 0.50
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


def configure(policy: str) -> None:
    base.BUDGETS = runner.BUDGETS
    base.MODEL_API_DOMAINS = runner.MODEL_API_DOMAINS
    base.heartbeat_for = runner.heartbeat_for
    base.migration_every = runner.migration_every
    base.DIAGNOSTICS = DIAGNOSTICS
    base.ROLE_FILE = runner.POLICY_ROLES[policy]
    base.TASK_FILES = TASK_FILES
    base.TASKS = TASKS
    base.SMOOTH_TASK = SMOOTH_TASK
    base.RUGGED_TASK = RUGGED_TASK
    base.CONDITIONS = CONDITIONS
    base.INITIAL_SALT = "coral-threshold-v3"
    base.AGENT_TIMEOUT = 240
    base.PRACTICAL_DELTA_Z = PRACTICAL_DELTA_Z
    base.CONTRAST_METRICS = (*base.CONTRAST_METRICS[:6], *BEHAVIOR_METRICS)


def mechanism_decision(
    rows: list[dict[str, Any]],
    contrasts: list[dict[str, Any]],
    *,
    policy: str,
    repetitions: int,
) -> dict[str, Any]:
    budgets: list[dict[str, Any]] = []
    earliest: int | None = None
    for budget in runner.BUDGETS:
        rugged = next(
            (
                row
                for row in contrasts
                if row["task"] == RUGGED_TASK
                and row["budget"] == budget
                and row["contrast"] == "multi_island_4_minus_global_8"
            ),
            None,
        )
        interaction = next(
            (
                row
                for row in contrasts
                if row["task"] == "rugged_minus_smooth" and row["budget"] == budget
            ),
            None,
        )
        global_rows = [
            row
            for row in rows
            if row["task"] == RUGGED_TASK
            and row["budget"] == budget
            and row["condition"] == "global_8"
        ]
        adoption = (
            statistics.fmean(
                float(row["inferred_cross_agent_adoption_rate"]) for row in global_rows
            )
            if global_rows
            else 0.0
        )
        lineage_difference = (
            float(rugged["mean_active_inferred_lineages_difference"]) if rugged is not None else 0.0
        )
        lineage_low = (
            float(rugged["mean_active_inferred_lineages_ci_low"]) if rugged is not None else 0.0
        )
        ready = (
            rugged is not None
            and interaction is not None
            and repetitions == 8
            and len(global_rows) == 8
        )
        manipulation_passes = (
            ready
            and adoption >= MIN_HIGH_DIFFUSION_ADOPTION
            and lineage_difference >= MIN_ACTIVE_LINEAGE_DIFFERENCE
            and lineage_low > 0
        )
        score_passes = bool(interaction is not None and interaction["threshold_rule_passes"])
        full_passes = policy == "high_diffusion" and manipulation_passes and score_passes
        budgets.append(
            {
                "budget": budget,
                "confirmatory_ready": ready,
                "observed_global_adoption_rate": adoption,
                "active_lineage_difference": lineage_difference,
                "active_lineage_ci_low": lineage_low,
                "manipulation_passes": manipulation_passes,
                "score_rule_passes": score_passes,
                "full_mechanism_rule_passes": full_passes,
            }
        )
        if full_passes and earliest is None:
            earliest = budget
    return {
        "policy": policy,
        "registered_repetitions": 8,
        "minimum_high_diffusion_adoption_rate": MIN_HIGH_DIFFUSION_ADOPTION,
        "minimum_active_lineage_difference": MIN_ACTIVE_LINEAGE_DIFFERENCE,
        "practical_delta_random_z": PRACTICAL_DELTA_Z,
        "earliest_supported_multi_island_threshold": earliest,
        "budget_manipulation_checks": budgets,
        "interpretation": (
            "causal mechanism-positive confirmation"
            if policy == "high_diffusion"
            else "endogenous social-learning observation; never pooled with high diffusion"
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy",
        choices=tuple(runner.POLICY_ROLES),
        required=True,
    )
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--tasks", nargs="+", choices=TASKS, default=list(TASKS))
    parser.add_argument("--conditions", nargs="+", choices=CONDITIONS, default=list(CONDITIONS))
    parser.add_argument("--budgets", nargs="+", type=int, default=list(runner.BUDGETS))
    parser.add_argument("--repetitions", type=int, default=8)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure(args.policy)
    if any(budget not in runner.BUDGETS for budget in args.budgets):
        raise SystemExit("analysis requested an unregistered threshold-v3 budget")
    results_root = args.results_root or Path(
        f"/var/tmp/coral-institutions-results/nk-threshold-v3/{args.policy}"
    )
    output = args.output_dir or ROOT / f"threshold_v3_analysis_{args.policy}"
    references = base.diagnostics()
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    superseded: list[dict[str, Any]] = []
    expected = 0
    for budget in args.budgets:
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
                            rejected.append(
                                {"run_dir": str(run_dir), "reasons": ["missing identity"]}
                            )
                            continue
                        row = base.collect(run_dir, identity, task, budget, references)
                        row["policy"] = args.policy
                        reasons = base.integrity(run_dir, identity, task, budget, row)
                        if reasons:
                            rejected.append(
                                {
                                    "run_dir": str(run_dir),
                                    "reasons": reasons,
                                    "observed": row,
                                }
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
    contrasts, _score_threshold = base.make_contrasts(rows, args.repetitions)
    base.write_csv(output / "contrasts.csv", contrasts)
    decision = mechanism_decision(rows, contrasts, policy=args.policy, repetitions=args.repetitions)
    (output / "threshold.json").write_text(json.dumps(decision, indent=2) + "\n")
    audit = {
        "schema_version": 3,
        "policy": args.policy,
        "primary_metric": "final best random-baseline z-score",
        "primary_contrast": "multi_island_4 minus global_8 paired within held-out seed",
        "accepted_rows": len(rows),
        "expected_rows": expected,
        "integrity_failures": failures,
        "superseded_invalid_runs": superseded,
    }
    (output / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(
        f"Audited {len(rows)}/{expected} threshold-v3 {args.policy} cells; failures={len(failures)}"
    )
    if failures and not args.allow_incomplete:
        raise SystemExit(f"threshold-v3 matrix incomplete; see {output / 'audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
