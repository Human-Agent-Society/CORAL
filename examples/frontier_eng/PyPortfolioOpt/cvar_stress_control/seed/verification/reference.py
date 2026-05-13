import cvxpy as cp
import numpy as np


def solve_instance(instance: dict) -> dict:
    R = np.asarray(instance["scenario_returns"], dtype=float)
    mu = np.asarray(instance["mu"], dtype=float)
    w_prev = np.asarray(instance["w_prev"], dtype=float)
    lower = np.asarray(instance["lower"], dtype=float)
    upper = np.asarray(instance["upper"], dtype=float)
    sector_ids = np.asarray(instance["sector_ids"], dtype=int)
    sector_lower = instance["sector_lower"]
    sector_upper = instance["sector_upper"]
    beta = float(instance["beta"])
    target_return = float(instance["target_return"])
    turnover_limit = float(instance["turnover_limit"])

    T, n = R.shape
    w = cp.Variable(n)
    alpha = cp.Variable()
    u = cp.Variable(T)
    z = cp.Variable(n)

    cvar = alpha + (1.0 / ((1.0 - beta) * T)) * cp.sum(u)

    constraints = [
        cp.sum(w) == 1,
        w >= lower,
        w <= upper,
        mu @ w >= target_return,
        u >= 0,
        u >= -R @ w - alpha,
        z >= w - w_prev,
        z >= -(w - w_prev),
        z >= 0,
        cp.sum(z) <= turnover_limit,
    ]

    for s, lo in sector_lower.items():
        idx = np.where(sector_ids == int(s))[0]
        constraints.append(cp.sum(w[idx]) >= float(lo))

    for s, hi in sector_upper.items():
        idx = np.where(sector_ids == int(s))[0]
        constraints.append(cp.sum(w[idx]) <= float(hi))

    prob = cp.Problem(cp.Minimize(cvar), constraints)

    solved = False
    for solver in [cp.SCS, cp.ECOS, cp.OSQP]:
        try:
            prob.solve(solver=solver, verbose=False)
            if prob.status in {"optimal", "optimal_inaccurate"}:
                solved = True
                break
        except Exception:
            continue

    if not solved or w.value is None:
        raise RuntimeError(f"reference solver failed: {prob.status}")

    return {"weights": np.asarray(w.value).reshape(-1)}
