# EVOLVE-BLOCK-START
"""Baseline implementation for Task 05.

No stockpyl EOQD optimizer is used here.
"""

from __future__ import annotations

import math


def classic_eoq(fixed_cost: float, holding_cost: float, demand_rate: float) -> float:
    return math.sqrt(2.0 * fixed_cost * demand_rate / holding_cost)


def solve(cfg: dict):
    q_classic = classic_eoq(cfg["fixed_cost"], cfg["holding_cost"], cfg["demand_rate"])
    safety_multiplier = 1.0 + 0.5 * cfg["disruption_rate"] / cfg["recovery_rate"]
    q_manual = q_classic * safety_multiplier
    return q_classic, q_manual, safety_multiplier
# EVOLVE-BLOCK-END
