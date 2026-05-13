"""Stronger reference strategy for Task 1.

Modes:
- `auto` (default): use SciPy-based hybrid if available, otherwise heuristic local search.
- `hybrid_scipy`: heuristic assignment + differential-evolution power refinement.
- `heuristic`: deterministic local-search heuristic only.
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from optic.comm.metrics import theoryBER


def allocate_wdm_oracle(
    user_demands_gbps,
    channel_centers_hz,
    total_power_dbm,
    pmin_dbm=-10.0,
    pmax_dbm=7.0,
    target_ber=1e-3,
    seed=0,
    mode="auto",
    time_limit_s=10.0,
):
    mode = str(mode).lower()
    if mode not in {"auto", "hybrid_scipy", "heuristic"}:
        raise ValueError("mode must be one of: auto/hybrid_scipy/heuristic")

    demands = np.asarray(user_demands_gbps, dtype=float)
    n_channels = len(channel_centers_hz)

    heuristic = _solve_heuristic(
        demands=demands,
        n_channels=n_channels,
        total_power_dbm=total_power_dbm,
        pmin_dbm=pmin_dbm,
        pmax_dbm=pmax_dbm,
        target_ber=target_ber,
        seed=seed,
    )

    if mode == "heuristic":
        heuristic["__oracle_meta__"] = {
            "mode_used": "heuristic_local_search",
            "solver": "numpy_local_search",
            "optimal": False,
        }
        return heuristic

    de_fn = _maybe_import_differential_evolution()
    if de_fn is None:
        heuristic["__oracle_meta__"] = {
            "mode_used": "heuristic_local_search",
            "solver": "numpy_local_search",
            "status": "scipy_unavailable",
            "optimal": False,
        }
        return heuristic

    hybrid = _solve_hybrid_scipy(
        demands=demands,
        base_assignment=np.asarray(heuristic["assignment"], dtype=int),
        base_power=np.asarray(heuristic["power_dbm"], dtype=float),
        n_channels=n_channels,
        total_power_dbm=total_power_dbm,
        pmin_dbm=pmin_dbm,
        pmax_dbm=pmax_dbm,
        target_ber=target_ber,
        seed=seed,
        time_limit_s=time_limit_s,
        differential_evolution=de_fn,
    )
    if mode == "hybrid_scipy":
        hybrid["__oracle_meta__"] = {
            "mode_used": "hybrid_scipy_de",
            "solver": "scipy_differential_evolution",
            "optimal": False,
            "time_limit_s": float(time_limit_s),
        }
        return hybrid

    # auto: choose better proxy objective between heuristic and hybrid.
    h_obj = _proxy_objective(
        assignment=np.asarray(heuristic["assignment"], dtype=int),
        power_dbm=np.asarray(heuristic["power_dbm"], dtype=float),
        demands=demands,
        target_ber=target_ber,
    )
    hy_obj = _proxy_objective(
        assignment=np.asarray(hybrid["assignment"], dtype=int),
        power_dbm=np.asarray(hybrid["power_dbm"], dtype=float),
        demands=demands,
        target_ber=target_ber,
    )

    if hy_obj > h_obj:
        hybrid["__oracle_meta__"] = {
            "mode_used": "hybrid_scipy_de",
            "solver": "scipy_differential_evolution",
            "optimal": False,
            "time_limit_s": float(time_limit_s),
            "selected_by_proxy": True,
        }
        return hybrid

    heuristic["__oracle_meta__"] = {
        "mode_used": "heuristic_local_search",
        "solver": "numpy_local_search",
        "optimal": False,
        "selected_by_proxy": True,
    }
    return heuristic


def _solve_hybrid_scipy(
    demands,
    base_assignment,
    base_power,
    n_channels,
    total_power_dbm,
    pmin_dbm,
    pmax_dbm,
    target_ber,
    seed,
    time_limit_s,
    differential_evolution,
):
    assignment = np.asarray(base_assignment, dtype=int).copy()
    power_dbm = np.asarray(base_power, dtype=float).copy()

    active_channels = np.unique(assignment[assignment >= 0])
    if active_channels.size == 0:
        return {"assignment": assignment, "power_dbm": power_dbm}

    def decode(x):
        p = np.full(n_channels, pmin_dbm, dtype=float)
        p[active_channels] = np.clip(np.asarray(x, dtype=float), pmin_dbm, pmax_dbm)
        return _renormalize_active_power(
            power_dbm=p,
            assignment=assignment,
            n_channels=n_channels,
            total_power_dbm=total_power_dbm,
            pmin_dbm=pmin_dbm,
            pmax_dbm=pmax_dbm,
        )

    def objective(x):
        p = decode(x)
        return -_proxy_objective(
            assignment=assignment,
            power_dbm=p,
            demands=demands,
            target_ber=target_ber,
        )

    bounds = [(pmin_dbm, pmax_dbm)] * active_channels.size
    maxiter = int(np.clip(8 + 2 * float(time_limit_s), 8, 40))
    popsize = 6

    res = differential_evolution(
        objective,
        bounds=bounds,
        maxiter=maxiter,
        popsize=popsize,
        seed=int(seed),
        polish=False,
        updating="deferred",
    )
    p_best = decode(np.asarray(res.x))
    return {"assignment": assignment, "power_dbm": p_best}


def _solve_heuristic(demands, n_channels, total_power_dbm, pmin_dbm, pmax_dbm, target_ber, seed):
    rng = np.random.default_rng(seed)

    assignment = _initial_assignment(demands, n_channels)
    power_dbm = _initial_power(
        demands=demands,
        assignment=assignment,
        n_channels=n_channels,
        total_power_dbm=total_power_dbm,
        pmin_dbm=pmin_dbm,
        pmax_dbm=pmax_dbm,
    )

    best_assignment = assignment.copy()
    best_power = power_dbm.copy()
    best_obj = _proxy_objective(
        assignment=best_assignment,
        power_dbm=best_power,
        demands=demands,
        target_ber=target_ber,
    )

    for _ in range(260):
        cand_assignment = best_assignment.copy()
        cand_power = best_power.copy()

        action = rng.random()
        if action < 0.35:
            _move_user_to_unused_channel(cand_assignment, n_channels, rng)
        elif action < 0.70:
            _swap_two_users(cand_assignment, rng)
        else:
            _perturb_active_power(cand_assignment, cand_power, rng)

        cand_power = _renormalize_active_power(
            power_dbm=cand_power,
            assignment=cand_assignment,
            n_channels=n_channels,
            total_power_dbm=total_power_dbm,
            pmin_dbm=pmin_dbm,
            pmax_dbm=pmax_dbm,
        )

        cand_obj = _proxy_objective(
            assignment=cand_assignment,
            power_dbm=cand_power,
            demands=demands,
            target_ber=target_ber,
        )
        if cand_obj > best_obj:
            best_obj = cand_obj
            best_assignment = cand_assignment
            best_power = cand_power

    return {"assignment": best_assignment, "power_dbm": best_power}


def _initial_assignment(demands, n_channels):
    n_users = demands.size
    n_served = min(n_users, n_channels)

    spaced = _evenly_spaced_channels(n_channels, n_served)
    center = (n_channels - 1) / 2.0
    ch_order = spaced[np.argsort(np.abs(spaced - center))]

    user_order = np.argsort(-demands)
    assignment = -np.ones(n_users, dtype=int)
    for k in range(n_served):
        assignment[user_order[k]] = int(ch_order[k])
    return assignment


def _initial_power(demands, assignment, n_channels, total_power_dbm, pmin_dbm, pmax_dbm):
    power_dbm = np.full(n_channels, pmin_dbm, dtype=float)
    used = np.where(assignment >= 0)[0]
    if used.size == 0:
        return power_dbm

    ch = assignment[used]
    demand_w = np.maximum(demands[used], 1e-9)
    demand_w = demand_w / np.sum(demand_w)

    active_budget = _active_budget_lin(total_power_dbm, n_channels, ch.size, pmin_dbm)
    plin = active_budget * demand_w
    pdbm = 10.0 * np.log10(np.maximum(plin, 1e-12))
    pdbm = np.clip(pdbm, pmin_dbm, pmax_dbm)

    power_dbm[ch] = pdbm
    return _renormalize_active_power(
        power_dbm=power_dbm,
        assignment=assignment,
        n_channels=n_channels,
        total_power_dbm=total_power_dbm,
        pmin_dbm=pmin_dbm,
        pmax_dbm=pmax_dbm,
    )


def _evenly_spaced_channels(n_channels, n_served):
    if n_served <= 0:
        return np.array([], dtype=int)
    raw = np.linspace(0, n_channels - 1, n_served)
    cand = np.rint(raw).astype(int)
    cand = np.clip(cand, 0, n_channels - 1)
    used = set()
    out = []
    for c in cand:
        if c not in used:
            used.add(int(c))
            out.append(int(c))
    if len(out) < n_served:
        for c in range(n_channels):
            if c not in used:
                used.add(c)
                out.append(c)
            if len(out) == n_served:
                break
    return np.asarray(sorted(out), dtype=int)


def _move_user_to_unused_channel(assignment, n_channels, rng):
    users = np.where(assignment >= 0)[0]
    if users.size == 0:
        return
    used_channels = set(int(x) for x in assignment[users])
    free = [c for c in range(n_channels) if c not in used_channels]
    if not free:
        return
    u = int(rng.choice(users))
    assignment[u] = int(rng.choice(free))


def _swap_two_users(assignment, rng):
    users = np.where(assignment >= 0)[0]
    if users.size < 2:
        return
    u1, u2 = rng.choice(users, size=2, replace=False)
    assignment[u1], assignment[u2] = assignment[u2], assignment[u1]


def _perturb_active_power(assignment, power_dbm, rng):
    channels = np.unique(assignment[assignment >= 0])
    if channels.size == 0:
        return
    c = int(rng.choice(channels))
    power_dbm[c] += rng.normal(0.0, 0.7)


def _active_budget_lin(total_power_dbm, n_channels, n_active, pmin_dbm):
    total_lin = 10 ** (float(total_power_dbm) / 10.0)
    inactive_lin = (n_channels - n_active) * (10 ** (float(pmin_dbm) / 10.0))
    return max(total_lin - inactive_lin, n_active * (10 ** (float(pmin_dbm) / 10.0)))


def _renormalize_active_power(power_dbm, assignment, n_channels, total_power_dbm, pmin_dbm, pmax_dbm):
    p = np.asarray(power_dbm, dtype=float).copy()
    active_channels = np.unique(assignment[assignment >= 0])
    if active_channels.size == 0:
        return p

    target_active = _active_budget_lin(total_power_dbm, n_channels, active_channels.size, pmin_dbm)

    plin = 10 ** (p[active_channels] / 10.0)
    s = np.sum(plin)
    if s <= 0:
        plin = np.ones_like(plin)
        s = np.sum(plin)
    plin *= target_active / s
    p[active_channels] = np.clip(10.0 * np.log10(np.maximum(plin, 1e-12)), pmin_dbm, pmax_dbm)

    total_budget_lin = 10 ** (float(total_power_dbm) / 10.0)
    now_lin = np.sum(10 ** (p / 10.0))
    if now_lin > total_budget_lin * 1.000001:
        active_lin = 10 ** (p[active_channels] / 10.0)
        inactive_lin = np.sum(10 ** (p[np.setdiff1d(np.arange(n_channels), active_channels)] / 10.0))
        target_active_rescale = max(total_budget_lin - inactive_lin, 1e-12)
        scale = target_active_rescale / max(np.sum(active_lin), 1e-12)
        active_lin *= min(scale, 1.0)
        p[active_channels] = np.clip(10.0 * np.log10(np.maximum(active_lin, 1e-12)), pmin_dbm, pmax_dbm)
    return p


def _proxy_objective(assignment, power_dbm, demands, target_ber):
    M = 4
    capacity_scale = 28.0
    noise_floor_lin = 2e-3
    interference_scale = 0.12
    interference_decay = 0.9

    n_users = len(assignment)
    n_channels = len(power_dbm)
    assigned = assignment >= 0
    if not np.any(assigned):
        return -1e12

    user_snr_db = np.full(n_users, -30.0)
    user_ber = np.ones(n_users)
    user_capacity = np.zeros(n_users)

    for u in range(n_users):
        ch = int(assignment[u])
        if ch < 0:
            continue
        sig = 10 ** (power_dbm[ch] / 10.0)
        interf = 0.0
        for v in range(n_users):
            ch2 = int(assignment[v])
            if v == u or ch2 < 0:
                continue
            interf += (10 ** (power_dbm[ch2] / 10.0)) * np.exp(-abs(ch - ch2) / interference_decay)

        snr_lin = sig / (noise_floor_lin + interference_scale * interf)
        snr_db = 10.0 * np.log10(max(snr_lin, 1e-12))
        user_snr_db[u] = snr_db

        ebn0_db = snr_db - 10.0 * np.log10(np.log2(M))
        user_ber[u] = float(theoryBER(M, ebn0_db, "qam"))
        user_capacity[u] = capacity_scale * np.log2(1.0 + max(snr_lin, 1e-12))

    sat = np.minimum(user_capacity / np.maximum(demands, 1e-9), 1.0)
    demand_satisfaction = float(np.mean(sat))
    ber_pass = float(np.mean(user_ber[assigned] <= target_ber))
    spectral_util = float(np.sum(assigned) / max(n_channels, 1))
    avg_snr_db = float(np.mean(user_snr_db[assigned]))
    snr_term = np.clip((avg_snr_db - 5.0) / 20.0, 0.0, 1.0)
    return 0.35 * demand_satisfaction + 0.40 * ber_pass + 0.05 * spectral_util + 0.20 * snr_term


def _maybe_import_differential_evolution():
    try:
        from scipy.optimize import differential_evolution
        return differential_evolution
    except Exception:
        local = Path(__file__).resolve().parents[3] / ".third_party"
        if local.exists() and str(local) not in sys.path:
            sys.path.insert(0, str(local))
        try:
            from scipy.optimize import differential_evolution
            return differential_evolution
        except Exception:
            return None
