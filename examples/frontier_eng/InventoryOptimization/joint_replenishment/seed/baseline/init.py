# EVOLVE-BLOCK-START
"""Baseline implementation for Task 03.

No stockpyl optimizer is used here.
"""

from __future__ import annotations


def solve() -> dict:
    """Fixed-cycle + demand-bucket multiples heuristic."""

    base_cycle = 1.5
    demand_rates = [120.0, 90.0, 60.0, 40.0, 25.0, 18.0, 12.0, 8.0]

    multiples = []
    for d_i in demand_rates:
        if d_i >= 60:
            m_i = 1
        elif d_i >= 25:
            m_i = 2
        elif d_i >= 12:
            m_i = 3
        else:
            m_i = 4
        multiples.append(m_i)

    order_quantities = [d_i * m_i * base_cycle for d_i, m_i in zip(demand_rates, multiples)]

    return {
        "base_cycle_time": base_cycle,
        "order_multiples": multiples,
        "order_quantities": order_quantities,
    }
# EVOLVE-BLOCK-END
