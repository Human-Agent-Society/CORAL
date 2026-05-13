"""Reference implementation for Task 05 (uses stockpyl EOQD solver)."""

from __future__ import annotations

from stockpyl.supply_uncertainty import eoq_with_disruptions


def solve(cfg: dict) -> float:
    q_opt, _ = eoq_with_disruptions(
        cfg["fixed_cost"],
        cfg["holding_cost"],
        cfg["stockout_cost"],
        cfg["demand_rate"],
        cfg["disruption_rate"],
        cfg["recovery_rate"],
        approximate=False,
    )
    return float(q_opt)
