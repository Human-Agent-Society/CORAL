# EVOLVE-BLOCK-START
"""Baseline for Task 3: DSP mode scheduling (EDC vs DBP)."""

from __future__ import annotations

import numpy as np


def choose_dsp_mode(user_features, latency_budget_s, max_dbp_users=None, seed=0):
    """Choose per-user DSP mode.

    Output mode convention:
    - 0: EDC (low latency, lower quality)
    - 1: DBP (higher latency, higher quality)
    """
    est_snr_db = np.asarray(user_features["est_snr_db"], dtype=float)
    edc_latency = np.asarray(user_features["edc_latency_s"], dtype=float)
    dbp_latency = np.asarray(user_features["dbp_latency_s"], dtype=float)

    n_users = len(est_snr_db)
    mode = np.zeros(n_users, dtype=int)

    order = np.argsort(est_snr_db)  # worse links first

    latency = float(np.sum(edc_latency))
    count_dbp = 0

    for u in order:
        if max_dbp_users is not None and count_dbp >= max_dbp_users:
            break
        extra = dbp_latency[u] - edc_latency[u]
        if latency + extra <= latency_budget_s:
            mode[u] = 1
            latency += extra
            count_dbp += 1

    return {"mode": mode}
# EVOLVE-BLOCK-END
