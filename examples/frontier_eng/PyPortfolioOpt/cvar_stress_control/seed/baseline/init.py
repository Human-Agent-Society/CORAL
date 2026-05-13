# EVOLVE-BLOCK-START
import numpy as np


def _project_with_bounds(w: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    w = np.minimum(np.maximum(w, lower), upper)
    for _ in range(30):
        gap = 1.0 - w.sum()
        if abs(gap) < 1e-10:
            break
        free = (w > lower + 1e-12) & (w < upper - 1e-12)
        if not np.any(free):
            break
        w[free] += gap / free.sum()
        w = np.minimum(np.maximum(w, lower), upper)
    s = w.sum()
    if s <= 0:
        return np.ones_like(w) / w.size
    return w / s


def _enforce_sector(
    w: np.ndarray,
    sector_ids: np.ndarray,
    sector_lower: dict,
    sector_upper: dict,
    lower: np.ndarray,
    upper: np.ndarray,
) -> np.ndarray:
    w = w.copy()
    for _ in range(6):
        changed = False
        for s in np.unique(sector_ids):
            idx = np.where(sector_ids == s)[0]
            lo = sector_lower.get(int(s), 0.0)
            hi = sector_upper.get(int(s), 1.0)
            sec = w[idx].sum()
            if sec < lo - 1e-10:
                need = lo - sec
                room = upper[idx] - w[idx]
                room_sum = room.sum()
                if room_sum > 1e-12:
                    add = np.minimum(room, need * room / room_sum)
                    w[idx] += add
                    changed = True
            elif sec > hi + 1e-10:
                excess = sec - hi
                room = w[idx] - lower[idx]
                room_sum = room.sum()
                if room_sum > 1e-12:
                    sub = np.minimum(room, excess * room / room_sum)
                    w[idx] -= sub
                    changed = True
        w = _project_with_bounds(w, lower, upper)
        if not changed:
            break
    return w


def _enforce_turnover(w: np.ndarray, w_prev: np.ndarray, turnover_limit: float) -> np.ndarray:
    d = w - w_prev
    l1 = np.abs(d).sum()
    if l1 <= turnover_limit + 1e-12:
        return w
    scale = turnover_limit / max(l1, 1e-12)
    return w_prev + scale * d


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

    tail_q = max(1, int((1.0 - beta) * R.shape[0]))
    losses_by_asset = -R
    sorted_losses = np.sort(losses_by_asset, axis=0)
    tail_risk = sorted_losses[-tail_q:, :].mean(axis=0)

    score = mu / (tail_risk + 1e-6)
    score = np.maximum(score, 0.0)
    if score.sum() < 1e-12:
        w = np.ones_like(mu) / mu.size
    else:
        w = score / score.sum()

    w = _project_with_bounds(w, lower, upper)
    w = _enforce_sector(w, sector_ids, sector_lower, sector_upper, lower, upper)
    w = _enforce_turnover(w, w_prev, turnover_limit)
    w = _project_with_bounds(w, lower, upper)

    # Greedy return tilt if below target: move weight from low-mu to high-mu assets.
    order_hi = np.argsort(-mu)
    order_lo = np.argsort(mu)
    for _ in range(200):
        ret = float(mu @ w)
        if ret >= target_return - 1e-10:
            break
        improved = False
        for j in order_hi[:8]:
            room_add = upper[j] - w[j]
            if room_add <= 1e-10:
                continue
            for i in order_lo[:12]:
                if mu[j] <= mu[i] + 1e-12:
                    continue
                room_sub = w[i] - lower[i]
                if room_sub <= 1e-10:
                    continue
                step = min(0.005, room_add, room_sub)
                if step <= 0:
                    continue
                w_try = w.copy()
                w_try[j] += step
                w_try[i] -= step
                w_try = _enforce_sector(
                    w_try, sector_ids, sector_lower, sector_upper, lower, upper
                )
                w_try = _enforce_turnover(w_try, w_prev, turnover_limit)
                w_try = _project_with_bounds(w_try, lower, upper)
                if mu @ w_try > mu @ w + 1e-10:
                    w = w_try
                    improved = True
                    break
            if improved:
                break
        if not improved:
            break

    return {"weights": w}
# EVOLVE-BLOCK-END
