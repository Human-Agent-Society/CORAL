#!/usr/bin/env python3
"""Evaluator for high_availability_tight_deadline_large_overhead variant."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from run_evaluator import main
from __init__ import HIGH_AVAILABILITY_SCENARIOS, TIGHT_DEADLINE, LARGE_OVERHEAD

if __name__ == "__main__":
    main(
        str(Path(__file__).resolve().parent / "resources"),
        scenarios=HIGH_AVAILABILITY_SCENARIOS,
        deadline_hours=TIGHT_DEADLINE,
        restart_overhead_hours=LARGE_OVERHEAD,
    )
