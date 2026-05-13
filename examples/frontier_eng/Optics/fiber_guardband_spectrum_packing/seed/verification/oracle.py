"""Stronger reference for Task 4.

Modes:
- `auto` (default): compare hybrid search and exact-geometry (if available), choose better proxy score.
- `hybrid`: deterministic local search over user order + best-fit packing.
- `exact_geometry`: OR-Tools CP-SAT model for geometry objective.
- `heuristic`: small-demand-first + best-fit.
"""

from __future__ import annotations

from pathlib import Path
import sys
import time

import numpy as np


def pack_spectrum_oracle(
    user_demand_slots,
    n_slots,
    guard_slots=1,
    seed=0,
    mode="auto",
    time_limit_s=12.0,
):
    d = np.asarray(user_demand_slots, dtype=int)
    mode = str(mode).lower()
    if mode not in {"auto", "hybrid", "exact_geometry", "heuristic"}:
        raise ValueError("mode must be one of: auto/hybrid/exact_geometry/heuristic")

    if mode == "heuristic":
        alloc = _pack_from_order(np.argsort(d), d, n_slots, guard_slots)
        return {"alloc": alloc, "__oracle_meta__": {"mode_used": "heuristic_small_first_best_fit", "solver": "numpy"}}

    if mode == "hybrid":
        alloc = _hybrid_local_search(d, n_slots, guard_slots, seed=seed, time_limit_s=time_limit_s)
        return {
            "alloc": alloc,
            "__oracle_meta__": {
                "mode_used": "hybrid_local_search",
                "solver": "numpy_local_search",
                "time_limit_s": float(time_limit_s),
            },
        }

    if mode == "exact_geometry":
        cp_model = _maybe_import_cp_sat()
        if cp_model is not None:
            solved = _solve_exact_geometry_cp_sat(
                cp_model=cp_model,
                d=d,
                n_slots=n_slots,
                guard_slots=guard_slots,
                time_limit_s=time_limit_s,
            )
            if solved is not None:
                alloc, meta = solved
                return {"alloc": alloc, "__oracle_meta__": meta}
        # fallback
        alloc = _hybrid_local_search(d, n_slots, guard_slots, seed=seed, time_limit_s=time_limit_s)
        return {
            "alloc": alloc,
            "__oracle_meta__": {
                "mode_used": "hybrid_fallback_no_exact_geometry",
                "solver": "numpy_local_search",
                "status": "cp_sat_unavailable_or_no_solution",
                "time_limit_s": float(time_limit_s),
            },
        }

    # auto mode: pick better proxy among available strategies.
    cand = []

    alloc_h = _hybrid_local_search(d, n_slots, guard_slots, seed=seed, time_limit_s=time_limit_s)
    cand.append(
        (
            _proxy_score(alloc_h, d, n_slots),
            alloc_h,
            {"mode_used": "hybrid_local_search", "solver": "numpy_local_search", "time_limit_s": float(time_limit_s)},
        )
    )

    cp_model = _maybe_import_cp_sat()
    if cp_model is not None:
        solved = _solve_exact_geometry_cp_sat(
            cp_model=cp_model,
            d=d,
            n_slots=n_slots,
            guard_slots=guard_slots,
            time_limit_s=time_limit_s,
        )
        if solved is not None:
            alloc_e, meta_e = solved
            cand.append((_proxy_score(alloc_e, d, n_slots), alloc_e, meta_e))

    best = max(cand, key=lambda x: x[0])
    return {"alloc": best[1], "__oracle_meta__": best[2]}


def _hybrid_local_search(d, n_slots, guard_slots, seed, time_limit_s):
    rng = np.random.default_rng(seed)
    n_users = len(d)

    current_order = np.argsort(d)
    current_alloc = _pack_from_order(current_order, d, n_slots, guard_slots)
    current_obj = _proxy_score(current_alloc, d, n_slots)

    best_order = current_order.copy()
    best_alloc = current_alloc.copy()
    best_obj = current_obj

    t0 = time.time()
    max_steps = 6000
    for step in range(max_steps):
        if time.time() - t0 > max(float(time_limit_s), 0.5):
            break

        cand_order = current_order.copy()
        r = rng.random()
        if r < 0.55:
            i, j = rng.integers(0, n_users, size=2)
            cand_order[i], cand_order[j] = cand_order[j], cand_order[i]
        elif r < 0.85:
            i, j = sorted(rng.integers(0, n_users, size=2))
            if j > i:
                cand_order[i:j] = cand_order[i + 1 : j + 1]
                cand_order[j] = current_order[i]
        else:
            i, j = sorted(rng.integers(0, n_users, size=2))
            sub = cand_order[i : j + 1].copy()
            rng.shuffle(sub)
            cand_order[i : j + 1] = sub

        cand_alloc = _pack_from_order(cand_order, d, n_slots, guard_slots)
        cand_obj = _proxy_score(cand_alloc, d, n_slots)

        temp = max(0.02, 0.12 * (1.0 - step / max_steps))
        if cand_obj > current_obj or rng.random() < np.exp((cand_obj - current_obj) / temp):
            current_order = cand_order
            current_alloc = cand_alloc
            current_obj = cand_obj
            if cand_obj > best_obj:
                best_obj = cand_obj
                best_order = cand_order.copy()
                best_alloc = cand_alloc.copy()

    del best_order
    return best_alloc


def _pack_from_order(order, d, n_slots, guard_slots):
    alloc = [(-1, 0) for _ in range(len(d))]
    occupied = np.zeros(n_slots, dtype=bool)

    for u in order:
        width = int(d[u])
        if width <= 0 or width > n_slots:
            continue

        best = None
        for s in range(0, n_slots - width + 1):
            left = max(0, s - guard_slots)
            right = min(n_slots, s + width + guard_slots)
            if np.any(occupied[left:right]):
                continue

            occ_tmp = occupied.copy()
            occ_tmp[s : s + width] = True
            frag = _free_block_count(occ_tmp)
            key = (frag, s)
            if best is None or key < best[0]:
                best = (key, s)

        if best is not None:
            s = best[1]
            occupied[s : s + width] = True
            alloc[u] = (s, width)

    return np.asarray(alloc, dtype=int)


def _solve_exact_geometry_cp_sat(cp_model, d, n_slots, guard_slots, time_limit_s):
    n_users = len(d)
    model = cp_model.CpModel()

    starts = []
    for u in range(n_users):
        width = int(d[u])
        user_vars = []
        for s in range(0, n_slots - width + 1):
            user_vars.append((s, model.NewBoolVar(f"x_{u}_{s}")))
        starts.append(user_vars)
        model.Add(sum(v for _, v in user_vars) <= 1)

    # Guard-expanded non-overlap.
    for t in range(n_slots):
        cover = []
        for u in range(n_users):
            width = int(d[u])
            for s, var in starts[u]:
                left = max(0, s - guard_slots)
                right = min(n_slots, s + width + guard_slots)
                if left <= t < right:
                    cover.append(var)
        if cover:
            model.Add(sum(cover) <= 1)

    accepted_expr = []
    used_slot_expr = []
    for u in range(n_users):
        width = int(d[u])
        accepted_u = sum(var for _, var in starts[u])
        accepted_expr.append(accepted_u)
        for _, var in starts[u]:
            used_slot_expr.append(width * var)

    # Prioritize accepted users first, then total used slots.
    model.Maximize(10_000 * sum(accepted_expr) + sum(used_slot_expr))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(max(time_limit_s, 0.5))
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    alloc = np.full((n_users, 2), [-1, 0], dtype=int)
    for u in range(n_users):
        width = int(d[u])
        for s, var in starts[u]:
            if solver.Value(var) > 0:
                alloc[u] = [s, width]
                break

    meta = {
        "mode_used": "exact_geometry_cp_sat",
        "solver": "ortools_cp_sat",
        "status": solver.StatusName(status),
        "optimal": bool(status == cp_model.OPTIMAL),
        "time_limit_s": float(max(time_limit_s, 0.5)),
    }
    return alloc, meta


def _proxy_score(alloc, d, n_slots):
    accepted = alloc[:, 0] >= 0
    acceptance_ratio = float(np.mean(accepted))

    used = 0
    for i in range(len(alloc)):
        if accepted[i]:
            used += int(alloc[i, 1])
    utilization = used / max(n_slots, 1)

    occ = np.zeros(n_slots, dtype=bool)
    for i in range(len(alloc)):
        if accepted[i]:
            s, w = int(alloc[i, 0]), int(alloc[i, 1])
            occ[s : s + w] = True
    compactness = 1.0 / (1.0 + _free_block_count(occ))

    # Proxy aligned with verification score trend (without BER term).
    return 0.82 * acceptance_ratio + 0.08 * utilization + 0.10 * compactness


def _free_block_count(occupied):
    blocks = 0
    in_free = False
    for x in occupied:
        if not x and not in_free:
            blocks += 1
            in_free = True
        elif x:
            in_free = False
    return blocks


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
