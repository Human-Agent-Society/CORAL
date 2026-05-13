# EVOLVE-BLOCK-START
"""Baseline solver for Task 2: MCS + power scheduling."""

from __future__ import annotations

import numpy as np


def select_mcs_power(
    user_demands_gbps,
    channel_quality_db,
    total_power_dbm,
    mcs_candidates=(4, 16, 64),
    pmin_dbm=-8.0,
    pmax_dbm=4.0,
    target_ber=1e-3,
    seed=0,
):
    demands = np.asarray(user_demands_gbps, dtype=float)
    quality = np.asarray(channel_quality_db, dtype=float)
    mcs_candidates = np.asarray(mcs_candidates, dtype=int)

    n_users = demands.size

    # Simple threshold rule on quality
    mcs = np.full(n_users, int(mcs_candidates[0]), dtype=int)
    if np.any(mcs_candidates == 16):
        mcs[quality >= 15.0] = 16
    if np.any(mcs_candidates == 64):
        mcs[quality >= 22.0] = 64

    # Equal power split
    total_lin = 10 ** (float(total_power_dbm) / 10.0)
    each_lin = total_lin / max(n_users, 1)
    each_dbm = 10.0 * np.log10(max(each_lin, 1e-12))
    each_dbm = np.clip(each_dbm, pmin_dbm, pmax_dbm)

    power_dbm = np.full(n_users, each_dbm, dtype=float)

    return {"mcs": mcs, "power_dbm": power_dbm}
# EVOLVE-BLOCK-END
