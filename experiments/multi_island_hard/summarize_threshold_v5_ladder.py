#!/usr/bin/env python3
"""Summarize complete per-budget v5 held-out analyses into a threshold ladder."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import run_threshold_v5_mechanism as runner


def summarize(
    results_root: Path,
    *,
    budgets: tuple[int, ...],
    repetitions: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for budget in budgets:
        budget_root = results_root / f"budget-{budget}"
        audit_path = budget_root / "scripted-mechanism-audit.json"
        analysis_path = budget_root / "scripted-mechanism-analysis.json"
        try:
            audit = json.loads(audit_path.read_text())
            analysis = json.loads(analysis_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"budget {budget}: missing or invalid audit/analysis: {exc}")
            continue
        audit_complete = bool(
            audit.get("registered_budget")
            and audit.get("valid_cells") == audit.get("expected_cells")
            and not audit.get("matrix_errors")
            and int(audit.get("budget", -1)) == budget
            and int(audit.get("repetitions", -1)) == repetitions
        )
        decision = analysis.get("decision", {})
        analysis_complete = bool(
            int(analysis.get("budget", -1)) == budget
            and int(analysis.get("repetitions", -1)) == repetitions
            and decision.get("confirmatory_ready")
        )
        if not audit_complete or not analysis_complete:
            errors.append(f"budget {budget}: incomplete registered audit or analysis")
            continue
        rows.append(
            {
                "budget": budget,
                "rugged_beats_global": bool(decision.get("rugged_beats_global")),
                "rugged_beats_partition": bool(
                    decision.get("rugged_beats_partition")
                ),
                "hard_smooth_global_beats_multi": bool(
                    decision.get("hard_smooth_global_beats_multi")
                ),
                "hard_smooth_unsolved": bool(decision.get("hard_smooth_unsolved")),
                "threshold_rule_passes": bool(
                    decision.get("confirmatory_mechanism_threshold_passes")
                ),
            }
        )
    supported = [row["budget"] for row in rows if row["threshold_rule_passes"]]
    return {
        "schema_version": 1,
        "registered_budgets": list(budgets),
        "registered_repetitions": repetitions,
        "complete_budgets": [row["budget"] for row in rows],
        "errors": errors,
        "rows": rows,
        "earliest_supported_multi_island_threshold": min(supported)
        if supported
        else None,
        "interpretation": (
            "Held-out scripted mechanism threshold only. Smoke results are excluded, "
            "cross-family effects are not pooled, and natural/real-task evidence remains required."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=runner.RESULTS_ROOT)
    parser.add_argument(
        "--budgets",
        type=int,
        nargs="+",
        default=list(runner.CONFIRMATORY_BUDGETS),
    )
    parser.add_argument("--repetitions", type=int, default=8)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    budgets = tuple(sorted(set(args.budgets)))
    if budgets != runner.CONFIRMATORY_BUDGETS or args.repetitions != 8:
        raise SystemExit("v5 ladder summary requires all registered budgets and eight seeds")
    root = args.results_root.resolve()
    result = summarize(root, budgets=budgets, repetitions=args.repetitions)
    output = args.output or root / "scripted-mechanism-ladder.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["errors"] and not args.allow_incomplete:
        raise SystemExit(f"v5 threshold ladder incomplete; see {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
