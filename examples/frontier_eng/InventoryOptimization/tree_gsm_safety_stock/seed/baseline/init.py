# EVOLVE-BLOCK-START
"""Baseline implementation for Task 01.

This module intentionally avoids stockpyl and only contains a simple
rule-based CST assignment.
"""

from __future__ import annotations

PROCESSING_TIME = {
    1: 2.0,
    3: 1.0,
    2: 1.0,
    4: 1.0,
}


def solve(_unused=None) -> dict[int, int]:
    """Rule-based CST policy.

    Rule:
    - demand-facing nodes follow SLA directly
    - internal nodes use processing-time threshold
    """

    cst = {2: 0, 4: 1}
    for idx, processing_time in PROCESSING_TIME.items():
        if idx in cst:
            continue
        cst[idx] = 1 if float(processing_time) >= 2.0 else 0

    return cst
# EVOLVE-BLOCK-END
