"""Reference implementation for Task 02 (uses stockpyl optimizer)."""

from __future__ import annotations

from stockpyl.meio_general import meio_by_enumeration
from stockpyl.supply_chain_network import network_from_edges

STOCKOUT_COST = {10: 0.0, 20: 0.0, 30: 0.0, 40: 10.0, 50: 9.0}


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


def solve() -> dict[int, int]:
    net = build_network(1.0)
    best_s, _ = meio_by_enumeration(
        network=net,
        base_stock_levels={
            10: [24, 30, 36],
            20: [14, 18, 24],
            30: [14, 18, 24],
            40: [16, 20, 26],
            50: [16, 20, 26],
        },
        groups=[{20, 30}, {40, 50}],
        sim_num_trials=1,
        sim_num_periods=120,
        sim_rand_seed=11,
        progress_bar=False,
    )
    return {int(k): int(v) for k, v in best_s.items()}
