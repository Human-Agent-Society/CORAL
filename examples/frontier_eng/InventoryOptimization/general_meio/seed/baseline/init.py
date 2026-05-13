# EVOLVE-BLOCK-START
"""Baseline implementation for Task 02.

No stockpyl optimizer is used here.
"""

from __future__ import annotations


def solve() -> dict[int, int]:
    """Manual demand-coverage heuristic for base-stock levels."""

    mean_40 = 8.0
    mean_50 = 7.0
    sink_total = mean_40 + mean_50

    s40 = round(2.0 * mean_40)
    s50 = round(2.0 * mean_50)
    s20 = round(0.93 * sink_total)
    s30 = round(0.93 * sink_total)
    s10 = round(1.73 * sink_total)

    return {10: s10, 20: s20, 30: s30, 40: s40, 50: s50}
# EVOLVE-BLOCK-END
