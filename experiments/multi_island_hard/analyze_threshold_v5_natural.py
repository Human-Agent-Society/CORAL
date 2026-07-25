#!/usr/bin/env python3
"""Analyze only integrity-valid v5 natural-agent topology cells."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import analyze_threshold_v5_mechanism as common
from experiments.multi_island_hard import run_threshold_v5_natural as runner

METRICS = (
    "final_best",
    "random_z_final_best",
    "best_so_far_auc",
    "midpoint_diversity",
    "final_diversity",
    "duplicate_candidate_rate",
    "mean_active_inferred_lineages",
    "final_inferred_lineages",
    "inferred_cross_agent_adoption_rate",
)


def contrasts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = {
        (str(row["task"]), str(row["condition"]), int(row["repetition"])): row for row in rows
    }
    grouped: defaultdict[tuple[str, str, str], list[float]] = defaultdict(list)
    tasks = sorted({str(row["task"]) for row in rows})
    for task in tasks:
        repetitions = sorted(
            int(row["repetition"])
            for row in rows
            if row["task"] == task and row["condition"] == "global_8"
        )
        for repetition in repetitions:
            multi = indexed[(task, "multi_island_4", repetition)]
            for control in ("global_8", "partition_4"):
                reference = indexed[(task, control, repetition)]
                for metric in METRICS:
                    left = multi.get(metric)
                    right = reference.get(metric)
                    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                        grouped[(task, f"multi_island_4_minus_{control}", metric)].append(
                            float(left) - float(right)
                        )
    output: list[dict[str, Any]] = []
    for (task, contrast, metric), values in sorted(grouped.items()):
        low, high = common.bootstrap(values, f"v5-natural:{task}:{contrast}:{metric}")
        output.append(
            {
                "task": task,
                "contrast": contrast,
                "metric": metric,
                "paired_repetitions": len(values),
                "mean_difference": sum(values) / len(values),
                "bootstrap_ci_low": low,
                "bootstrap_ci_high": high,
                "paired_differences": values,
            }
        )
    return output


def decision(
    rows: list[dict[str, Any]],
    paired: list[dict[str, Any]],
    *,
    rugged_task: str,
    repetitions: int,
) -> dict[str, Any]:
    primary = [
        row
        for row in paired
        if row["task"] == rugged_task and row["metric"] == "final_best"
    ]
    primary_random_z = [
        row
        for row in paired
        if row["task"] == rugged_task and row["metric"] == "random_z_final_best"
    ]
    floors = {
        "multi_island_4_minus_global_8": common.BOUNDARY_EFFECT_FLOOR_RANDOM_Z,
        "multi_island_4_minus_partition_4": common.MIGRATION_EFFECT_FLOOR_RANDOM_Z,
    }
    multi_cells = [row for row in rows if row["condition"] == "multi_island_4"]
    confirmatory = bool(
        repetitions == 8
        and len(primary) == 2
        and len(primary_random_z) == 2
        and all(int(row["paired_repetitions"]) == 8 for row in primary)
        and all(int(row["paired_repetitions"]) == 8 for row in primary_random_z)
        and all(float(row["bootstrap_ci_low"]) > 0 for row in primary)
        and all(
            float(row["bootstrap_ci_low"]) > 0
            and float(row["mean_difference"]) >= floors[str(row["contrast"])]
            for row in primary_random_z
        )
        and multi_cells
        and all(
            int(row.get("post_migration_migrant_submission_events", 0)) > 0
            for row in multi_cells
        )
    )
    return {
        "confirmatory_natural_agent_threshold_passes": confirmatory,
        "primary_task": rugged_task,
        "primary_metric": "final_best",
        "requires_positive_multi_minus_global_and_partition_ci": True,
        "boundary_effect_floor_random_z": common.BOUNDARY_EFFECT_FLOOR_RANDOM_Z,
        "migration_effect_floor_random_z": common.MIGRATION_EFFECT_FLOOR_RANDOM_Z,
        "requires_practical_random_z_floors": True,
        "requires_post_migration_migrant_submissions": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=runner.RESULTS_ROOT)
    parser.add_argument("--repetitions", type=int, default=8)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selection = runner.mechanism.registered_selection()
    budget = selection["budget"]
    budget_root = args.results_root.resolve() / f"budget-{budget}"
    audit_path = args.audit or budget_root / "natural-agent-audit.json"
    audit = json.loads(audit_path.read_text())
    if (
        audit.get("valid_cells") != audit.get("expected_cells")
        or audit.get("matrix_errors")
        or int(audit.get("budget", -1)) != budget
        or int(audit.get("repetitions", -1)) != args.repetitions
    ):
        raise SystemExit("natural-agent analysis requires a complete matching audit")
    rugged = runner.mechanism.RUGGED_TASKS[selection["k"]]
    rows = [dict(row) for row in audit["cells"]]
    references = common.rugged_random_references(selection)
    for row in rows:
        reference = references.get(int(row["repetition"]))
        row["random_z_final_best"] = (
            (float(row["final_best"]) - reference[0]) / reference[1]
            if row["task"] == rugged and reference is not None
            else None
        )
    paired = contrasts(rows)
    natural_decision = decision(
        rows,
        paired,
        rugged_task=rugged,
        repetitions=args.repetitions,
    )
    result = {
        "schema_version": 1,
        "budget": budget,
        "repetitions": args.repetitions,
        "rows": rows,
        "contrasts": paired,
        "decision": natural_decision,
        "interpretation": (
            "Natural-agent topology evidence only. Smooth and Rugged effects remain "
            "separate, and structured real-task evidence is still required."
        ),
    }
    output = args.output or budget_root / "natural-agent-analysis.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            [
                row
                for row in paired
                if row["task"] == rugged
                and row["metric"] in {"final_best", "random_z_final_best"}
            ],
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
