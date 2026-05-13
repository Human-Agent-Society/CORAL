"""Reference implementation for Task 01 (uses stockpyl optimizer)."""

from __future__ import annotations

from stockpyl.gsm_tree import optimize_committed_service_times, preprocess_tree
from stockpyl.supply_chain_network import network_from_edges


def build_tree(demand_scale: float = 1.0):
    net = network_from_edges(
        edges=[(1, 3), (3, 2), (3, 4)],
        node_order_in_lists=[1, 3, 2, 4],
        local_holding_cost={1: 0.4, 3: 0.7, 2: 1.1, 4: 1.0},
        processing_time={1: 2, 3: 1, 2: 1, 4: 1},
        demand_bound_constant={1: 1, 3: 1, 2: 1, 4: 1},
        external_inbound_cst={1: 1, 3: 0, 2: 0, 4: 0},
        external_outbound_cst={1: 100, 3: 100, 2: 0, 4: 1},
        demand_type={2: "N", 4: "N"},
        mean={2: 80, 4: 70},
        standard_deviation={2: 20 * demand_scale, 4: 22 * demand_scale},
    )
    return preprocess_tree(net)


def solve(nominal_tree=None) -> dict[int, int]:
    if nominal_tree is None:
        nominal_tree = build_tree(1.0)
    cst, _ = optimize_committed_service_times(nominal_tree)
    return cst
