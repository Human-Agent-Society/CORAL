# EVOLVE-BLOCK-START
"""Baseline for Task 4: spectrum packing with guard bands."""

from __future__ import annotations

import numpy as np


def pack_spectrum(user_demand_slots, n_slots, guard_slots=1, seed=0):
    """First-Fit Decreasing baseline.

    Returns
    -------
    dict with key `alloc`:
      alloc[i] = (start_slot, width)
      if not allocated: (-1, 0)
    """
    d = np.asarray(user_demand_slots, dtype=int)
    n_users = d.size

    alloc = [(-1, 0) for _ in range(n_users)]

    order = np.argsort(-d)  # larger requests first

    occupied = np.zeros(n_slots, dtype=bool)

    for u in order:
        width = int(d[u])
        if width <= 0 or width > n_slots:
            continue

        found = False
        for s in range(0, n_slots - width + 1):
            left = max(0, s - guard_slots)
            right = min(n_slots, s + width + guard_slots)
            if not np.any(occupied[left:right]):
                occupied[s : s + width] = True
                alloc[u] = (s, width)
                found = True
                break

        if not found:
            alloc[u] = (-1, 0)

    return {"alloc": np.asarray(alloc, dtype=int)}
# EVOLVE-BLOCK-END
