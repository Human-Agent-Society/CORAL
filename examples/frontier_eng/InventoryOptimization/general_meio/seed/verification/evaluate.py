#!/usr/bin/env python3
"""Evaluate baseline(init) vs reference(stockpyl) for Task 02."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from stockpyl.sim import simulation
from stockpyl.supply_chain_network import network_from_edges

TASK_DIR = Path(__file__).resolve().parents[1]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

from baseline.init import solve as solve_baseline  # noqa: E402
from verification.reference import solve as solve_reference  # noqa: E402

SINK_NODES = [40, 50]
STOCKOUT_COST = {10: 0.0, 20: 0.0, 30: 0.0, 40: 10.0, 50: 9.0}


def clip(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def build_network(demand_scale: float = 1.0):
    return network_from_edges(
        edges=[(10, 20), (10, 30), (20, 40), (30, 40), (20, 50), (30, 50)],
        node_order_in_lists=[10, 20, 30, 40, 50],
        shipment_lead_time={10: 1, 20: 1, 30: 1, 40: 0, 50: 0},
        local_holding_cost={10: 0.2, 20: 0.4, 30: 0.4, 40: 0.9, 50: 0.9},
        stockout_cost=STOCKOUT_COST,
        policy_type="BS",
        base_stock_level={10: 30, 20: 18, 30: 18, 40: 20, 50: 20},
        demand_type={40: "P", 50: "P"},
        mean={40: 8 * demand_scale, 50: 7 * demand_scale},
        standard_deviation={40: 3 * demand_scale, 50: 2.5 * demand_scale},
        supply_type={10: "U"},
    )


def evaluate_policy(base_stock_levels: dict[int, int], demand_scale: float, periods: int, seed: int):
    net = build_network(demand_scale)
    for n in net.nodes:
        n.inventory_policy.base_stock_level = base_stock_levels[n.index]

    simulation(net, num_periods=periods, rand_seed=seed, progress_bar=False)

    total_cost = 0.0
    holding_cost = 0.0
    stockout_cost = 0.0
    shortage_units = {k: 0.0 for k in SINK_NODES}

    expected_demand = {
        40: 8 * demand_scale * periods,
        50: 7 * demand_scale * periods,
    }

    for idx in net.node_indices:
        node = net.nodes_by_index[idx]
        for sv in node.state_vars[:periods]:
            total_cost += float(sv.total_cost_incurred)
            holding_cost += float(sv.holding_cost_incurred)
            stockout_cost += float(sv.stockout_cost_incurred)
            if idx in SINK_NODES and STOCKOUT_COST[idx] > 0:
                shortage_units[idx] += float(sv.stockout_cost_incurred) / STOCKOUT_COST[idx]

    fill_by_sink = {
        idx: clip(1.0 - shortage_units[idx] / max(expected_demand[idx], 1e-9)) for idx in SINK_NODES
    }
    weighted_fill = (
        fill_by_sink[40] * expected_demand[40] + fill_by_sink[50] * expected_demand[50]
    ) / (expected_demand[40] + expected_demand[50])

    return {
        "cost_per_period": total_cost / periods,
        "holding_per_period": holding_cost / periods,
        "stockout_per_period": stockout_cost / periods,
        "fill_rate": weighted_fill,
        "fill_by_sink": fill_by_sink,
    }


def score_solution(solution_s: dict[int, int]):
    baseline = {10: 30, 20: 18, 30: 18, 40: 20, 50: 20}

    base_nom = evaluate_policy(baseline, 1.0, 160, 11)
    sol_nom = evaluate_policy(solution_s, 1.0, 160, 11)
    base_stress = evaluate_policy(baseline, 1.2, 160, 17)
    sol_stress = evaluate_policy(solution_s, 1.2, 160, 17)

    cost_score = clip(
        (base_nom["cost_per_period"] - sol_nom["cost_per_period"])
        / (base_nom["cost_per_period"] - base_nom["cost_per_period"] * 0.65)
    )
    service_score = clip((sol_nom["fill_rate"] - 0.98) / (0.995 - 0.98))
    robustness_score = clip(
        (base_stress["cost_per_period"] - sol_stress["cost_per_period"])
        / (base_stress["cost_per_period"] - base_stress["cost_per_period"] * 0.85)
    )
    fill_gap = abs(sol_nom["fill_by_sink"][40] - sol_nom["fill_by_sink"][50])
    balance_score = clip(1.0 - fill_gap / 0.05)

    final_score = (
        0.30 * cost_score
        + 0.35 * service_score
        + 0.25 * robustness_score
        + 0.10 * balance_score
    )

    return {
        "solution_base_stock": solution_s,
        "nominal": {"baseline": base_nom, "solution": sol_nom},
        "stress": {"baseline": base_stress, "solution": sol_stress},
        "metrics": {
            "cost_score": cost_score,
            "service_score": service_score,
            "robustness_score": robustness_score,
            "balance_score": balance_score,
        },
        "weights": {
            "cost_score": 0.30,
            "service_score": 0.35,
            "robustness_score": 0.25,
            "balance_score": 0.10,
        },
        "final_score": final_score,
    }


def main() -> None:
    output_dir = TASK_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_solution = solve_baseline()
    reference_solution = solve_reference()

    baseline_result = {
        "task": "general_meio",
        "method": "baseline",
        "algorithm": "manual demand-coverage rule",
        **score_solution(baseline_solution),
    }
    reference_result = {
        "task": "general_meio",
        "method": "reference",
        "algorithm": "stockpyl MEIO enumeration",
        **score_solution(reference_solution),
    }

    comparison = {
        "task": "general_meio",
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
