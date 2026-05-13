# EVOLVE-BLOCK-START
"""Baseline implementation for Task 04.

No stockpyl DP solver is used here.
"""

from __future__ import annotations


def solve(demand_mean, demand_sd):
    """Manual moment-based time-varying policy.

    Rule:
    - s_t = round(0.60 * mean_t)
    - S_t = round(mean_t + 1.10 * sd_t + 32), with S_t >= s_t + 6
    """

    s_levels = [round(0.60 * m) for m in demand_mean]
    S_levels = []
    for i, (m, sd) in enumerate(zip(demand_mean, demand_sd)):
        s_t = s_levels[i]
        S_t = round(m + 1.10 * sd + 32)
        S_levels.append(max(S_t, s_t + 6))

    return s_levels, S_levels
# EVOLVE-BLOCK-END
