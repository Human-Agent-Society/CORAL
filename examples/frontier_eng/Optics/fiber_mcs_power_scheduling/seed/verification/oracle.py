"""Stronger reference for Task 2.

Modes:
- `auto` (default): try OR-Tools CP-SAT exact solve, fallback to deterministic DP.
- `exact`: force CP-SAT attempt first (still falls back if dependency unavailable).
- `heuristic`: use deterministic DP directly.
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from optic.comm.metrics import theoryBER


def select_mcs_power_oracle(
    user_demands_gbps,
    channel_quality_db,
    total_power_dbm,
    mcs_candidates=(4, 16, 64),
    pmin_dbm=-8.0,
    pmax_dbm=4.0,
    target_ber=1e-3,
    seed=0,
    mode="auto",
    time_limit_s=20.0,
):
    del seed  # deterministic reference policy
    mode = str(mode).lower()
    if mode not in {"auto", "exact", "heuristic"}:
        raise ValueError("mode must be one of: auto/exact/heuristic")

    demands = np.asarray(user_demands_gbps, dtype=float)
    quality = np.asarray(channel_quality_db, dtype=float)
    mcs_candidates = np.asarray(mcs_candidates, dtype=int)

    cp_model = _maybe_import_cp_sat() if mode in {"auto", "exact"} else None
    if cp_model is not None:
        exact = _solve_exact_cp_sat(
            cp_model=cp_model,
            demands=demands,
            quality=quality,
            total_power_dbm=total_power_dbm,
            mcs_candidates=mcs_candidates,
            pmin_dbm=pmin_dbm,
            pmax_dbm=pmax_dbm,
            target_ber=target_ber,
            time_limit_s=time_limit_s,
        )
        if exact is not None:
            result, meta = exact
            result["__oracle_meta__"] = meta
            return result

    result = _solve_dp_fallback(
        demands=demands,
        quality=quality,
        total_power_dbm=total_power_dbm,
        mcs_candidates=mcs_candidates,
        pmin_dbm=pmin_dbm,
        pmax_dbm=pmax_dbm,
        target_ber=target_ber,
    )
    result["__oracle_meta__"] = {
        "mode_requested": mode,
        "mode_used": "dp_fallback",
        "solver": "numpy_dp",
        "status": "ok",
        "optimal": False,
    }
    return result


def _solve_exact_cp_sat(
    cp_model,
    demands,
    quality,
    total_power_dbm,
    mcs_candidates,
    pmin_dbm,
    pmax_dbm,
    target_ber,
    time_limit_s,
):
    n_users = len(demands)
    power_levels_dbm = np.arange(pmin_dbm, pmax_dbm + 1e-12, 0.5)

    # Integerized power budget.
    cost_unit = 0.02  # mW
    budget_lin = 10 ** (float(total_power_dbm) / 10.0)
    cap = int(np.floor(budget_lin / cost_unit + 1e-9))

    # Build per-user option table.
    options_per_user = []
    for u in range(n_users):
        options = []
        for M in mcs_candidates:
            for p_dbm in power_levels_dbm:
                cost_lin = 10 ** (float(p_dbm) / 10.0)
                cost_int = int(np.ceil(cost_lin / cost_unit - 1e-12))
                util = _option_utility(
                    demand=float(demands[u]),
                    quality_db=float(quality[u]),
                    mcs=int(M),
                    power_dbm=float(p_dbm),
                    mcs_max=int(np.max(mcs_candidates)),
                    target_ber=target_ber,
                )
                options.append((cost_int, util, int(M), float(p_dbm)))
        options_per_user.append(options)

    model = cp_model.CpModel()
    choose = []
    util_scale = 1_000_000

    for u in range(n_users):
        user_vars = []
        for k, (cost_int, util, _, _) in enumerate(options_per_user[u]):
            v = model.NewBoolVar(f"x_{u}_{k}")
            user_vars.append((v, cost_int, int(round(util * util_scale))))
        choose.append(user_vars)
        model.Add(sum(v for v, _, _ in user_vars) == 1)

    model.Add(
        sum(cost * v for user_vars in choose for v, cost, _ in user_vars) <= cap
    )
    model.Maximize(sum(u * v for user_vars in choose for v, _, u in user_vars))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(max(time_limit_s, 0.5))
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    mcs = np.zeros(n_users, dtype=int)
    power_dbm = np.zeros(n_users, dtype=float)
    for u in range(n_users):
        for k, (cost_int, util, M, p_dbm) in enumerate(options_per_user[u]):
            del cost_int, util
            if solver.Value(choose[u][k][0]) > 0:
                mcs[u] = int(M)
                power_dbm[u] = float(p_dbm)
                break

    meta = {
        "mode_requested": "auto_or_exact",
        "mode_used": "exact_cp_sat",
        "solver": "ortools_cp_sat",
        "status": solver.StatusName(status),
        "optimal": bool(status == cp_model.OPTIMAL),
        "time_limit_s": float(max(time_limit_s, 0.5)),
        "cost_unit_mw": cost_unit,
    }
    return {"mcs": mcs, "power_dbm": power_dbm}, meta


def _solve_dp_fallback(
    demands,
    quality,
    total_power_dbm,
    mcs_candidates,
    pmin_dbm,
    pmax_dbm,
    target_ber,
):
    n_users = demands.size
    power_levels_dbm = np.arange(pmin_dbm, pmax_dbm + 1e-12, 0.5)

    budget_lin = 10 ** (float(total_power_dbm) / 10.0)
    cost_unit = 0.02  # mW
    cap = int(np.floor(budget_lin / cost_unit + 1e-9))

    options_per_user = []
    for u in range(n_users):
        opts = []
        for M in mcs_candidates:
            for p_dbm in power_levels_dbm:
                cost_lin = 10 ** (p_dbm / 10.0)
                cost_int = int(np.ceil(cost_lin / cost_unit - 1e-12))

                util = _option_utility(
                    demand=demands[u],
                    quality_db=quality[u],
                    mcs=int(M),
                    power_dbm=float(p_dbm),
                    mcs_max=int(np.max(mcs_candidates)),
                    target_ber=target_ber,
                )
                opts.append((cost_int, util, int(M), float(p_dbm)))

        opts.sort(key=lambda x: (x[0], -x[1]))
        pruned = []
        best_util = -1e18
        for item in opts:
            if item[1] > best_util + 1e-12:
                pruned.append(item)
                best_util = item[1]
        options_per_user.append(pruned)

    dp = np.full((n_users + 1, cap + 1), -1e18, dtype=float)
    choice = np.zeros((n_users + 1, cap + 1), dtype=int)
    dp[0, :] = 0.0

    for i in range(1, n_users + 1):
        opts = options_per_user[i - 1]
        for b in range(cap + 1):
            best = -1e18
            best_k = 0
            for k, item in enumerate(opts):
                c, u, _, _ = item
                if c <= b:
                    v = dp[i - 1, b - c] + u
                    if v > best:
                        best = v
                        best_k = k
            dp[i, b] = best
            choice[i, b] = best_k

    b = int(np.argmax(dp[n_users, :]))
    mcs = np.zeros(n_users, dtype=int)
    power_dbm = np.zeros(n_users, dtype=float)

    for i in range(n_users, 0, -1):
        item = options_per_user[i - 1][choice[i, b]]
        c, _, M, p_dbm = item
        mcs[i - 1] = int(M)
        power_dbm[i - 1] = float(p_dbm)
        b -= c

    return {"mcs": mcs, "power_dbm": power_dbm}


def _option_utility(demand, quality_db, mcs, power_dbm, mcs_max, target_ber):
    snr_db = quality_db + power_dbm
    ebn0_db = snr_db - 10.0 * np.log10(np.log2(mcs))
    ber = float(theoryBER(mcs, ebn0_db, "qam"))

    cap = 32.0 * np.log2(mcs)
    if ber <= target_ber:
        reliability = 1.0
    else:
        reliability = np.exp(-(ber - target_ber) * 15.0)
    achieved = min(demand, cap * reliability)

    sat = min(achieved / max(demand, 1e-9), 1.0)
    ber_ok = 1.0 if ber <= target_ber else 0.0
    se = np.log2(mcs) / np.log2(max(mcs_max, 2))
    return 0.45 * sat + 0.40 * ber_ok + 0.15 * se


def _maybe_import_cp_sat():
    try:
        from ortools.sat.python import cp_model
        return cp_model
    except Exception:
        local = Path(__file__).resolve().parents[3] / ".third_party"
        if local.exists() and str(local) not in sys.path:
            sys.path.insert(0, str(local))
        try:
            from ortools.sat.python import cp_model
            return cp_model
        except Exception:
            return None
