"""Reference implementation for Task 04 (uses stockpyl DP solver)."""

from __future__ import annotations

from stockpyl.finite_horizon import finite_horizon_dp


def solve(cfg: dict):
    s_star, S_star, dp_expected_cost, *_ = finite_horizon_dp(
        num_periods=cfg["num_periods"],
        holding_cost=cfg["holding_cost"],
        stockout_cost=cfg["stockout_cost"],
        terminal_holding_cost=cfg["terminal_holding_cost"],
        terminal_stockout_cost=cfg["terminal_stockout_cost"],
        purchase_cost=cfg["purchase_cost"],
        fixed_cost=cfg["fixed_cost"],
        demand_mean=cfg["demand_mean"],
        demand_sd=cfg["demand_sd"],
        initial_inventory_level=cfg["initial_inventory_level"],
    )
    return s_star, S_star, float(dp_expected_cost)
