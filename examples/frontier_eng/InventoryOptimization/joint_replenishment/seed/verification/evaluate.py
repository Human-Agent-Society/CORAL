#!/usr/bin/env python3
"""Evaluate baseline(init) vs reference(stockpyl) for Task 03."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[1]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

from baseline.init import solve as solve_baseline  # noqa: E402
from verification.reference import solve as solve_reference  # noqa: E402


def clip(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def independent_eoq_cost(shared_fixed_cost, individual_fixed_costs, holding_costs, demand_rates):
    qs = []
    cycles = []
    total_cost = 0.0

    for k_i, h_i, d_i in zip(individual_fixed_costs, holding_costs, demand_rates):
        k_total = shared_fixed_cost + k_i
        q_i = math.sqrt(2.0 * k_total * d_i / h_i)
        c_i = k_total * d_i / q_i + h_i * q_i / 2.0
        qs.append(q_i)
        cycles.append(q_i / d_i)
        total_cost += c_i

    return qs, cycles, total_cost


def policy_cost(shared_fixed_cost, individual_fixed_costs, holding_costs, demand_rates, base_cycle, multiples):
    total_cost = shared_fixed_cost / base_cycle
    for k_i, h_i, d_i, m_i in zip(individual_fixed_costs, holding_costs, demand_rates, multiples):
        total_cost += k_i / (m_i * base_cycle) + h_i * d_i * (m_i * base_cycle) / 2.0
    return total_cost


def score_solution(solution: dict):
    shared_fixed_cost = 100.0
    individual_fixed_costs = [40.0, 35.0, 30.0, 28.0, 25.0, 22.0, 20.0, 18.0]
    holding_costs = [1.8, 2.0, 1.6, 1.7, 1.5, 1.9, 2.1, 1.4]
    demand_rates = [120.0, 90.0, 60.0, 40.0, 25.0, 18.0, 12.0, 8.0]

    base_q, base_cycles, baseline_cost = independent_eoq_cost(
        shared_fixed_cost,
        individual_fixed_costs,
        holding_costs,
        demand_rates,
    )

    cycle_times = [m * solution["base_cycle_time"] for m in solution["order_multiples"]]
    sol_cost = policy_cost(
        shared_fixed_cost,
        individual_fixed_costs,
        holding_costs,
        demand_rates,
        solution["base_cycle_time"],
        solution["order_multiples"],
    )

    cost_score = clip((baseline_cost - sol_cost) / (baseline_cost - baseline_cost * 0.50))
    responsiveness_score = clip((2.6 - max(cycle_times)) / (2.6 - 1.8))
    coordination_score = clip((len(demand_rates) - len(set(solution["order_multiples"]))) / (len(demand_rates) - 1))

    final_score = 0.55 * cost_score + 0.30 * responsiveness_score + 0.15 * coordination_score

    return {
        "inputs": {
            "shared_fixed_cost": shared_fixed_cost,
            "individual_fixed_costs": individual_fixed_costs,
            "holding_costs": holding_costs,
            "demand_rates": demand_rates,
        },
        "independent_reference": {
            "order_quantities": base_q,
            "cycle_times": base_cycles,
            "cost": baseline_cost,
        },
        "solution": {
            "base_cycle_time": solution["base_cycle_time"],
            "order_multiples": solution["order_multiples"],
            "order_quantities": solution["order_quantities"],
            "cycle_times": cycle_times,
            "cost": sol_cost,
        },
        "metrics": {
            "cost_score": cost_score,
            "responsiveness_score": responsiveness_score,
            "coordination_score": coordination_score,
        },
        "weights": {
            "cost_score": 0.55,
            "responsiveness_score": 0.30,
            "coordination_score": 0.15,
        },
        "final_score": final_score,
    }


def main() -> None:
    output_dir = TASK_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_solution = solve_baseline()
    reference_solution = solve_reference()

    baseline_result = {
        "task": "joint_replenishment",
        "method": "baseline",
        "algorithm": "fixed-cycle + demand-bucket multiples",
        **score_solution(baseline_solution),
    }
    reference_result = {
        "task": "joint_replenishment",
        "method": "reference",
        "algorithm": "stockpyl Silver JRP heuristic",
        **score_solution(reference_solution),
    }

    comparison = {
        "task": "joint_replenishment",
        "baseline_final_score": baseline_result["final_score"],
        "reference_final_score": reference_result["final_score"],
        "gap_reference_minus_baseline": reference_result["final_score"] - baseline_result["final_score"],
        "winner": "reference"
        if reference_result["final_score"] >= baseline_result["final_score"]
        else "baseline",
    }

    (output_dir / "baseline_result.json").write_text(json.dumps(baseline_result, indent=2), encoding="utf-8")
    (output_dir / "reference_result.json").write_text(json.dumps(reference_result, indent=2), encoding="utf-8")
    (output_dir / "comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")

    print(f"Baseline score:  {baseline_result['final_score']:.4f}")
    print(f"Reference score: {reference_result['final_score']:.4f}")
    print(f"Gap:             {comparison['gap_reference_minus_baseline']:.4f}")
    print(f"Saved outputs to {output_dir}")


if __name__ == "__main__":
    main()
