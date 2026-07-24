#!/usr/bin/env python3
"""Analyze the pre-registered budget–difficulty threshold matrix.

Each budget is collected in its own results root so a stopped or invalid
budget cannot silently replace a different cell.  The primary estimand is the
within-task, within-budget multi-island minus global contrast in normalized
reference gain.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from experiments.multi_island import analyze as base
from experiments.multi_island_hard import analyze_hard as hard

TASKS = ("smooth128", "rugged128_k24")
CONDITIONS = ("global", "partition", "multi_island")
REPETITIONS = 3
PRACTICAL_DELTA = 0.05


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-root",
        type=Path,
        default=Path("/var/tmp/coral-institutions-results/threshold-v1"),
    )
    parser.add_argument("--budgets", type=int, nargs="+", default=[24, 64, 128])
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "threshold")
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


def configure(budget: int) -> dict[str, dict[str, float]]:
    hard.configure_base()
    base.EXPECTED_ATTEMPTS = budget
    hard.EXPECTED_ATTEMPTS = budget
    base.REPETITIONS = REPETITIONS
    base.TASK_CONDITIONS = {task: CONDITIONS for task in TASKS}
    base.TASK_LABELS = hard.TASK_LABELS
    base.CONDITION_LABELS = hard.LABELS
    base.COLORS = hard.COLORS
    base.MIGRATION_EVERY = max(6, budget // 4)
    base.MIGRATION_RANK_WINDOW = max(6, budget // 4)
    base.MIGRATION_COOLDOWN = 6
    return hard.load_diagnostics(hard.ROOT / "landscape_diagnostics.json")


def bootstrap(values: list[float], seed_text: str) -> tuple[float, float]:
    seed = int.from_bytes(hashlib.sha256(seed_text.encode()).digest()[:8], "big")
    return base.bootstrap_ci(values, seed=seed)


def row(run: base.Run, budget: int, diagnostics: dict[str, dict[str, float]]) -> dict[str, Any]:
    values = hard.run_row(run, diagnostics)
    values.update(
        {
            "budget": budget,
            "diversity_eval_budget": hard.diversity(run, budget),
        }
    )
    return values


def integrity_reasons(
    run: base.Run, budget: int, expected_role: Path
) -> list[str]:
    reasons = list(run.configuration_errors)
    try:
        identity = json.loads((run.path / "operator-command.json").read_text())
        command = identity.get("command", [])
        role = next(
            (str(item) for item in command if str(item).startswith("agents.runtime_options.role_file=")),
            "",
        )
        expected = f"agents.runtime_options.role_file={expected_role}"
        if role != expected:
            reasons.append(f"role protocol={role!r}, expected {expected!r}")
    except (OSError, json.JSONDecodeError, AttributeError, TypeError):
        reasons.append("operator command is unreadable")

    private_path = run.path / ".coral" / "private" / f"{run.task}.json"
    frozen_path = hard.TASKDATA / f"{run.task}.json"
    if not private_path.is_file() or private_path.read_bytes() != frozen_path.read_bytes():
        reasons.append("private landscape does not match frozen taskdata")
    if run.grader_errors:
        reasons.append(f"{run.grader_errors} grader infrastructure error(s)")
    if run.tune_protocol_violations:
        reasons.append(f"{run.tune_protocol_violations} tune protocol violation(s)")
    if run.condition != "multi_island" and run.migrations:
        reasons.append("migration note recorded in no-migration condition")
    if run.total_real != budget:
        reasons.append(f"total real records={run.total_real}, expected {budget}")
    return reasons


def collect(
    root: Path, budget: int, diagnostics: dict[str, dict[str, float]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    runs, incomplete = base.discover_runs(root.resolve())
    rows = [row(run, budget, diagnostics) for run in runs]
    failures = list(incomplete)
    expected_role = hard.ROOT / "eval_protocol.md"
    for run in runs:
        reasons = integrity_reasons(run, budget, expected_role)
        if reasons:
            failures.append(
                {
                    "task": run.task,
                    "condition": run.condition,
                    "repetition": run.repetition,
                    "run_dir": str(run.path),
                    "reasons": reasons,
                }
            )
    return rows, failures


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in rows:
        grouped[(int(item["budget"]), str(item["task"]), str(item["condition"]))].append(item)
    output: list[dict[str, Any]] = []
    for budget in sorted({int(row["budget"]) for row in rows}):
        for task in TASKS:
            for condition in CONDITIONS:
                group = grouped[(budget, task, condition)]
                if not group:
                    continue
                item: dict[str, Any] = {
                    "budget": budget,
                    "task": task,
                    "condition": condition,
                    "n": len(group),
                }
                for metric in (
                    "reference_gain",
                    "best_so_far_auc_reference",
                    "random_z",
                    "diversity_eval_budget",
                ):
                    values = [float(row[metric]) for row in group]
                    low, high = bootstrap(values, f"summary:{budget}:{task}:{condition}:{metric}")
                    item[f"{metric}_mean"] = statistics.fmean(values)
                    item[f"{metric}_sd"] = statistics.stdev(values) if len(values) > 1 else 0.0
                    item[f"{metric}_ci_low"] = low
                    item[f"{metric}_ci_high"] = high
                item["null_scores_total"] = sum(int(row["null_scores"]) for row in group)
                item["runtime_errors_total"] = sum(int(row["runtime_errors"]) for row in group)
                item["migrations_total"] = sum(int(row["migrations"]) for row in group)
                output.append(item)
    return output


def make_contrasts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in rows:
        grouped[(int(item["budget"]), str(item["task"]), str(item["condition"]))].append(item)
    output: list[dict[str, Any]] = []
    for budget in sorted({int(row["budget"]) for row in rows}):
        for task in TASKS:
            for reference in ("global", "partition"):
                left = grouped[(budget, task, "multi_island")]
                right = grouped[(budget, task, reference)]
                item: dict[str, Any] = {
                    "budget": budget,
                    "task": task,
                    "contrast": f"multi_island_minus_{reference}",
                    "practical_delta": PRACTICAL_DELTA,
                }
                for metric in (
                    "reference_gain",
                    "best_so_far_auc_reference",
                    "random_z",
                    "diversity_eval_budget",
                ):
                    left_values = [float(row[metric]) for row in left]
                    right_values = [float(row[metric]) for row in right]
                    difference = statistics.fmean(left_values) - statistics.fmean(right_values)
                    low, high = base.bootstrap_difference(
                        left_values,
                        right_values,
                        seed=int.from_bytes(
                            hashlib.sha256(
                                f"contrast:{budget}:{task}:{reference}:{metric}".encode()
                            ).digest()[:8],
                            "big",
                        ),
                    )
                    item[f"{metric}_difference"] = difference
                    item[f"{metric}_ci_low"] = low
                    item[f"{metric}_ci_high"] = high
                item["meets_reference_threshold"] = (
                    reference == "global"
                    and item["reference_gain_difference"] >= PRACTICAL_DELTA
                    and item["reference_gain_ci_low"] > 0
                )
                output.append(item)
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    if any(budget < 1 for budget in args.budgets):
        raise SystemExit("budgets must be positive")
    all_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    expected_cells = len(TASKS) * len(CONDITIONS) * REPETITIONS
    for budget in args.budgets:
        diagnostics = configure(budget)
        budget_root = args.results_root / f"budget-{budget}"
        rows, budget_failures = collect(budget_root, budget, diagnostics)
        all_rows.extend(rows)
        failures.extend(
            [{"budget": budget, **failure} for failure in budget_failures]
        )

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary = summarize(all_rows)
    contrasts = make_contrasts(all_rows) if not failures else []
    write_csv(output / "runs.csv", all_rows)
    write_csv(output / "summary.csv", summary)
    write_csv(output / "contrasts.csv", contrasts)
    audit = {
        "schema_version": 1,
        "expected_cells_per_budget": expected_cells,
        "budgets": args.budgets,
        "complete_rows": len(all_rows),
        "expected_rows": expected_cells * len(args.budgets),
        "expected_attempts_per_budget": args.budgets,
        "practical_delta": PRACTICAL_DELTA,
        "reference_method": "fixed diagnostic multi-start greedy ascent; approximate, not global optimum",
        "integrity_failures": failures,
    }
    (output / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    if failures and not args.allow_incomplete:
        raise SystemExit(
            f"Threshold matrix incomplete or invalid; see {output / 'audit.json'}"
        )
    print(f"Audited {len(all_rows)} run cells; failures={len(failures)}")
    print(f"Summary:   {output / 'summary.csv'}")
    print(f"Contrasts: {output / 'contrasts.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
