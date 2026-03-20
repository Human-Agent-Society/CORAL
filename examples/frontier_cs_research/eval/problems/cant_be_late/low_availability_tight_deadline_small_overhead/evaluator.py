#!/usr/bin/env python3
"""Evaluator for low_availability_tight_deadline_small_overhead variant."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from run_evaluator import main
from __init__ import LOW_AVAILABILITY_REGIONS, TIGHT_DEADLINE_CONFIG, SMALL_OVERHEAD

if __name__ == "__main__":
    main(
        str(Path(__file__).resolve().parent / "resources"),
        env_paths=LOW_AVAILABILITY_REGIONS,
        job_configs=TIGHT_DEADLINE_CONFIG,
        changeover_delays=SMALL_OVERHEAD,
    )
