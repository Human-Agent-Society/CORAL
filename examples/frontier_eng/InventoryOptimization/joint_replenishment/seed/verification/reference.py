"""Reference implementation for Task 03 (uses stockpyl optimizer)."""

from __future__ import annotations

from stockpyl.eoq import joint_replenishment_problem_silver_heuristic


def solve() -> dict:
    shared_fixed_cost = 100.0
    individual_fixed_costs = [40.0, 35.0, 30.0, 28.0, 25.0, 22.0, 20.0, 18.0]
    holding_costs = [1.8, 2.0, 1.6, 1.7, 1.5, 1.9, 2.1, 1.4]
    demand_rates = [120.0, 90.0, 60.0, 40.0, 25.0, 18.0, 12.0, 8.0]

    opt_q, base_cycle_time, order_multiples, _ = joint_replenishment_problem_silver_heuristic(
        shared_fixed_cost,
        individual_fixed_costs,
        holding_costs,
        demand_rates,
    )

    return {
        "base_cycle_time": float(base_cycle_time),
        "order_multiples": [int(x) for x in order_multiples],
        "order_quantities": [float(x) for x in opt_q],
    }
