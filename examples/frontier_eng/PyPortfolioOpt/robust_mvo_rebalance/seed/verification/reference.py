import cvxpy as cp
import numpy as np


def solve_instance(instance: dict) -> dict:
    mu = np.asarray(instance["mu"], dtype=float)
    cov = np.asarray(instance["cov"], dtype=float)
    w_prev = np.asarray(instance["w_prev"], dtype=float)
    lower = np.asarray(instance["lower"], dtype=float)
    upper = np.asarray(instance["upper"], dtype=float)
    sector_ids = np.asarray(instance["sector_ids"], dtype=int)
    sector_lower = instance["sector_lower"]
    sector_upper = instance["sector_upper"]
    factor_loadings = np.asarray(instance["factor_loadings"], dtype=float)
    factor_lower = np.asarray(instance["factor_lower"], dtype=float)
    factor_upper = np.asarray(instance["factor_upper"], dtype=float)
    risk_aversion = float(instance["risk_aversion"])
    transaction_penalty = float(instance["transaction_penalty"])
    turnover_limit = float(instance["turnover_limit"])

    n = mu.size
    w = cp.Variable(n)

    obj = cp.Maximize(
        mu @ w
        - risk_aversion * cp.quad_form(w, cov)
        - transaction_penalty * cp.norm1(w - w_prev)
    )

    constraints = [
        cp.sum(w) == 1,
        w >= lower,
        w <= upper,
        cp.norm1(w - w_prev) <= turnover_limit,
        factor_loadings.T @ w >= factor_lower,
        factor_loadings.T @ w <= factor_upper,
    ]

    for s, lo in sector_lower.items():
        idx = np.where(sector_ids == int(s))[0]
        constraints.append(cp.sum(w[idx]) >= float(lo))

    for s, hi in sector_upper.items():
        idx = np.where(sector_ids == int(s))[0]
        constraints.append(cp.sum(w[idx]) <= float(hi))

    prob = cp.Problem(obj, constraints)
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
