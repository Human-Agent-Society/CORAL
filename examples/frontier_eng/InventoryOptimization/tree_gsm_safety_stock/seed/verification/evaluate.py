#!/usr/bin/env python3
"""Evaluate baseline(init) vs reference(stockpyl) for Task 01."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from stockpyl.gsm_helpers import solution_cost_from_cst

TASK_DIR = Path(__file__).resolve().parents[1]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

from baseline.init import solve as solve_baseline  # noqa: E402
from verification.reference import build_tree, solve as solve_reference  # noqa: E402


def clip(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def score_solution(solution_cst: dict[int, int]):
    nominal = build_tree(1.0)
    stress = build_tree(1.3)
    baseline_cst = {1: 0, 3: 0, 2: 0, 4: 0}

    base_cost_nom = float(solution_cost_from_cst(nominal, baseline_cst))
    sol_cost_nom = float(solution_cost_from_cst(nominal, solution_cst))
    base_cost_stress = float(solution_cost_from_cst(stress, baseline_cst))
    sol_cost_stress = float(solution_cost_from_cst(stress, solution_cst))

    cost_score = clip((base_cost_nom - sol_cost_nom) / (base_cost_nom - base_cost_nom * 0.50))
    robustness_score = clip(
        (base_cost_stress - sol_cost_stress) / (base_cost_stress - base_cost_stress * 0.50)
    )
    sla_compliance = sum(1 for i, m in {2: 0, 4: 1}.items() if solution_cst[i] <= m) / 2.0

    changed_nodes = sum(1 for k in baseline_cst if baseline_cst[k] != solution_cst[k])
    complexity_score = 1.0 if changed_nodes <= 1 else 0.0

    final_score = (
        0.35 * cost_score
        + 0.35 * robustness_score
        + 0.10 * sla_compliance
        + 0.20 * complexity_score
    )

    return {
        "solution_cst": solution_cst,
        "metrics": {
            "baseline_cost_nominal": base_cost_nom,
            "solution_cost_nominal": sol_cost_nom,
            "baseline_cost_stress": base_cost_stress,
            "solution_cost_stress": sol_cost_stress,
            "cost_score": cost_score,
            "robustness_score": robustness_score,
            "sla_compliance": sla_compliance,
            "complexity_score": complexity_score,
        },
        "weights": {
            "cost_score": 0.35,
            "robustness_score": 0.35,
            "sla_compliance": 0.10,
            "complexity_score": 0.20,
        },
        "final_score": final_score,
    }


def main() -> None:
    output_dir = TASK_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_solution = solve_baseline()
    reference_solution = solve_reference(build_tree(1.0))

    baseline_result = {
        "task": "tree_gsm_safety_stock",
        "method": "baseline",
        "algorithm": "rule-based CST assignment",
        **score_solution(baseline_solution),
    }
    reference_result = {
        "task": "tree_gsm_safety_stock",
        "method": "reference",
        "algorithm": "stockpyl GSM tree DP",
        **score_solution(reference_solution),
    }

    comparison = {
        "task": "tree_gsm_safety_stock",
        "baseline_final_score": baseline_result["final_score"],
        "reference_final_score": reference_result["final_score"],
        "gap_reference_minus_baseline": reference_result["final_score"] - baseline_result["final_score"],
        "winner": "reference"
        if reference_result["final_score"] >= baseline_result["final_score"]
        else "baseline",
    }

    (output_dir / "baseline_result.json").write_text(
        json.dumps(baseline_result, indent=2), encoding="utf-8"
    )
    (output_dir / "reference_result.json").write_text(
        json.dumps(reference_result, indent=2), encoding="utf-8"
    )
    (output_dir / "comparison.json").write_text(
        json.dumps(comparison, indent=2), encoding="utf-8"
    )

    print(f"Baseline score:  {baseline_result['final_score']:.4f}")
    print(f"Reference score: {reference_result['final_score']:.4f}")
    print(f"Gap:             {comparison['gap_reference_minus_baseline']:.4f}")
    print(f"Saved outputs to {output_dir}")


if __name__ == "__main__":
    main()
