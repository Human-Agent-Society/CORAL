#!/usr/bin/env python3
"""Evaluator for high_availability_loose_deadline_small_overhead variant."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from run_evaluator import main
from __init__ import HIGH_AVAILABILITY_REGIONS, LOOSE_DEADLINE_CONFIG, SMALL_OVERHEAD

if __name__ == "__main__":
    main(
        str(Path(__file__).resolve().parent / "resources"),
        env_paths=HIGH_AVAILABILITY_REGIONS,
        job_configs=LOOSE_DEADLINE_CONFIG,
        changeover_delays=SMALL_OVERHEAD,
    )
