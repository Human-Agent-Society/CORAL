import cvxpy as cp
import numpy as np


def _build_problem(instance: dict, integer: bool):
    prices = np.asarray(instance["prices"], dtype=float)
    lot_sizes = np.asarray(instance["lot_sizes"], dtype=float)
    current_lots = np.asarray(instance["current_lots"], dtype=float)
    target_weights = np.asarray(instance["target_weights"], dtype=float)
    portfolio_value = float(instance["portfolio_value"])
    fee_rate = float(instance["fee_rate"])
    turnover_limit_value = float(instance["turnover_limit_value"])
    max_lots = np.asarray(instance["max_lots"], dtype=float)

    unit = prices * lot_sizes
    target_dollar = target_weights * portfolio_value

    n = unit.size
    x = cp.Variable(n, integer=integer)
    u = cp.Variable(n)
    v = cp.Variable(n)

    traded_notional = cp.sum(cp.multiply(unit, v))
    spend = cp.sum(cp.multiply(unit, x)) + fee_rate * traded_notional

    constraints = [
        x >= 0,
        x <= max_lots,
        u >= cp.multiply(unit, x) - target_dollar,
        u >= -(cp.multiply(unit, x) - target_dollar),
        u >= 0,
        v >= x - current_lots,
        v >= -(x - current_lots),
        v >= 0,
        traded_notional <= turnover_limit_value,
        spend <= portfolio_value,
    ]

    objective = cp.Minimize(cp.sum(u) + fee_rate * traded_notional)
    return x, cp.Problem(objective, constraints)


def solve_instance(instance: dict) -> dict:
    x, prob = _build_problem(instance, integer=True)
    prob.solve(solver=cp.HIGHS, verbose=False)
    if prob.status not in {"optimal", "optimal_inaccurate"} or x.value is None:
        raise RuntimeError(f"reference MIP failed: {prob.status}")
    return {"lots": np.rint(np.asarray(x.value).reshape(-1)).astype(int)}


def solve_lp_relaxation(instance: dict) -> dict:
    x, prob = _build_problem(instance, integer=False)
    prob.solve(solver=cp.HIGHS, verbose=False)
    if prob.status not in {"optimal", "optimal_inaccurate"} or x.value is None:
        raise RuntimeError(f"LP relaxation failed: {prob.status}")
    return {"lots": np.asarray(x.value).reshape(-1), "objective": float(prob.value)}
