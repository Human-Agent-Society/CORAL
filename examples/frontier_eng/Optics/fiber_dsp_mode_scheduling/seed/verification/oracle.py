"""Stronger reference for Task 3.

Modes:
- `auto` (default): try OR-Tools CP-SAT exact solve, fallback to knapsack DP.
- `exact`: force CP-SAT attempt first (still falls back if dependency unavailable).
- `heuristic`: deterministic knapsack DP fallback.
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from optic.comm.metrics import theoryBER


def choose_dsp_mode_oracle(
    user_features,
    latency_budget_s,
    max_dbp_users=None,
    seed=0,
    mode="auto",
    time_limit_s=20.0,
):
    del seed  # deterministic reference
    mode = str(mode).lower()
    if mode not in {"auto", "exact", "heuristic"}:
        raise ValueError("mode must be one of: auto/exact/heuristic")

    est_snr = np.asarray(user_features["est_snr_db"], dtype=float)
    gain = np.asarray(user_features["dbp_gain_db"], dtype=float)
    w = np.asarray(user_features["traffic_weight"], dtype=float)
    edc_t = np.asarray(user_features["edc_latency_s"], dtype=float)
    dbp_t = np.asarray(user_features["dbp_latency_s"], dtype=float)

    target_ber = float(user_features.get("target_ber", 1e-3))
    M = int(user_features.get("modulation_order", 16))

    cp_model = _maybe_import_cp_sat() if mode in {"auto", "exact"} else None
    if cp_model is not None:
        exact = _solve_exact_cp_sat(
            cp_model=cp_model,
            est_snr=est_snr,
            gain=gain,
            w=w,
            edc_t=edc_t,
            dbp_t=dbp_t,
            latency_budget_s=latency_budget_s,
            max_dbp_users=max_dbp_users,
            M=M,
            target_ber=target_ber,
            time_limit_s=time_limit_s,
        )
        if exact is not None:
            result, meta = exact
            result["__oracle_meta__"] = meta
            return result

    result = _solve_knapsack_fallback(
        est_snr=est_snr,
        gain=gain,
        w=w,
        edc_t=edc_t,
        dbp_t=dbp_t,
        latency_budget_s=latency_budget_s,
        max_dbp_users=max_dbp_users,
        M=M,
        target_ber=target_ber,
    )
    result["__oracle_meta__"] = {
        "mode_requested": mode,
        "mode_used": "knapsack_dp_fallback",
        "solver": "numpy_dp",
        "status": "ok",
        "optimal": False,
    }
    return result


def _solve_exact_cp_sat(
    cp_model,
    est_snr,
    gain,
    w,
    edc_t,
    dbp_t,
    latency_budget_s,
    max_dbp_users,
    M,
    target_ber,
    time_limit_s,
):
    n = len(est_snr)

    # Per-user additive objective terms.
    term_edc = np.zeros(n, dtype=float)
    term_dbp = np.zeros(n, dtype=float)
    for i in range(n):
        ber_edc = _ber_from_snr(est_snr[i], M)
        ber_dbp = _ber_from_snr(est_snr[i] + gain[i], M)
        rel_edc = 1.0 if ber_edc <= target_ber else np.exp(-(ber_edc - target_ber) * 20.0)
        rel_dbp = 1.0 if ber_dbp <= target_ber else np.exp(-(ber_dbp - target_ber) * 20.0)
        ber_ok_edc = 1.0 if ber_edc <= target_ber else 0.0
        ber_ok_dbp = 1.0 if ber_dbp <= target_ber else 0.0

        term_edc[i] = 0.65 * (w[i] * rel_edc / np.sum(w)) + 0.30 * (ber_ok_edc / n) + 0.05 * (1.0 / n)
        term_dbp[i] = 0.65 * (w[i] * rel_dbp / np.sum(w)) + 0.30 * (ber_ok_dbp / n) + 0.05 * 0.0

    model = cp_model.CpModel()
    z = [model.NewBoolVar(f"dbp_{i}") for i in range(n)]

    # Latency constraint in integer microseconds.
    unit = 1e-6
    budget_int = int(np.floor(float(latency_budget_s) / unit + 1e-9))
    edc_int = np.rint(edc_t / unit).astype(int)
    extra_int = np.rint(np.maximum(dbp_t - edc_t, 0.0) / unit).astype(int)

    model.Add(sum(int(edc_int[i]) + int(extra_int[i]) * z[i] for i in range(n)) <= budget_int)
    if max_dbp_users is not None:
        model.Add(sum(z) <= int(max_dbp_users))

    scale = 1_000_000
    const_part = int(round(np.sum(term_edc) * scale))
    delta = np.rint((term_dbp - term_edc) * scale).astype(int)
    model.Maximize(const_part + sum(int(delta[i]) * z[i] for i in range(n)))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(max(time_limit_s, 0.5))
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    mode = np.array([int(solver.Value(v)) for v in z], dtype=int)
    mode = _enforce_latency_budget(mode, w, gain, edc_t, dbp_t, latency_budget_s)

    meta = {
        "mode_requested": "auto_or_exact",
        "mode_used": "exact_cp_sat",
        "solver": "ortools_cp_sat",
        "status": solver.StatusName(status),
        "optimal": bool(status == cp_model.OPTIMAL),
        "time_limit_s": float(max(time_limit_s, 0.5)),
        "latency_unit_s": unit,
    }
    return {"mode": mode}, meta


def _solve_knapsack_fallback(
    est_snr,
    gain,
    w,
    edc_t,
    dbp_t,
    latency_budget_s,
    max_dbp_users,
    M,
    target_ber,
):
    n = len(est_snr)
    gain_u = np.zeros(n)
    cost = np.maximum(dbp_t - edc_t, 0.0)

    for i in range(n):
        ber_edc = _ber_from_snr(est_snr[i], M)
        ber_dbp = _ber_from_snr(est_snr[i] + gain[i], M)
        u_edc = _user_utility(ber_edc, w[i], target_ber)
        u_dbp = _user_utility(ber_dbp, w[i], target_ber)
        gain_u[i] = u_dbp - u_edc

    budget_extra = float(latency_budget_s - np.sum(edc_t))
    if budget_extra <= 0:
        return {"mode": np.zeros(n, dtype=int)}

    scale = 1e-4  # 0.1ms resolution
    cap = int(np.floor(budget_extra / scale))
    item_cost = np.maximum((cost / scale).astype(int), 0)

    dp = np.full((n + 1, cap + 1), -1e18)
    take = np.zeros((n + 1, cap + 1), dtype=bool)
    dp[0, :] = 0.0

    for i in range(1, n + 1):
        c = item_cost[i - 1]
        v = gain_u[i - 1]
        for b in range(cap + 1):
            best = dp[i - 1, b]
            choose = False
            if c <= b:
                val = dp[i - 1, b - c] + v
                if val > best:
                    best = val
                    choose = True
            dp[i, b] = best
            take[i, b] = choose

    b = int(np.argmax(dp[n, :]))
    mode = np.zeros(n, dtype=int)
    for i in range(n, 0, -1):
        if take[i, b]:
            mode[i - 1] = 1
            b -= item_cost[i - 1]

    if max_dbp_users is not None and np.sum(mode) > max_dbp_users:
        idx = np.where(mode == 1)[0]
        ratio = gain_u[idx] / np.maximum(cost[idx], 1e-9)
        keep = idx[np.argsort(-ratio)[:max_dbp_users]]
        mode[:] = 0
        mode[keep] = 1

    mode = _enforce_latency_budget(mode, w, gain, edc_t, dbp_t, latency_budget_s)
    return {"mode": mode}


def _ber_from_snr(snr_db, M):
    ebn0 = snr_db - 10 * np.log10(np.log2(M))
    return float(theoryBER(M, ebn0, "qam"))


def _user_utility(ber, weight, target_ber):
    if ber <= target_ber:
        rel = 1.0
    else:
        rel = np.exp(-(ber - target_ber) * 20.0)
    return float(weight * rel)


def _enforce_latency_budget(mode, weight, gain, edc_t, dbp_t, latency_budget_s):
    mode = np.asarray(mode, dtype=int).copy()
    latency = float(np.sum(np.where(mode == 1, dbp_t, edc_t)))
    budget = float(latency_budget_s)
    if latency <= budget * 1.0005:
        return mode

    while latency > budget * 1.0005 and np.any(mode == 1):
        idx = np.where(mode == 1)[0]
        extra = np.maximum(dbp_t[idx] - edc_t[idx], 1e-12)
        ratio = (weight[idx] * gain[idx]) / extra
        drop = idx[np.argmin(ratio)]
        mode[drop] = 0
        latency = float(np.sum(np.where(mode == 1, dbp_t, edc_t)))
    return mode


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
