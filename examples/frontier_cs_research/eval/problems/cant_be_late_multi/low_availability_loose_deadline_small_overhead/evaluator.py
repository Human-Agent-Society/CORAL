#!/usr/bin/env python3
"""Evaluator for low_availability_loose_deadline_small_overhead variant."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from run_evaluator import main
from __init__ import LOW_AVAILABILITY_SCENARIOS, LOOSE_DEADLINE, SMALL_OVERHEAD

if __name__ == "__main__":
    main(
        str(Path(__file__).resolve().parent / "resources"),
        scenarios=LOW_AVAILABILITY_SCENARIOS,
        deadline_hours=LOOSE_DEADLINE,
        restart_overhead_hours=SMALL_OVERHEAD,
    )
