#!/usr/bin/env python3
"""Evaluator for N-body simulation problem (10k particles variant).

Solutions are C++ files that implement Simulator class and createSimulator().
"""

import sys
from pathlib import Path

# Add common directory to path
HERE = Path(__file__).resolve().parent
COMMON_DIR = HERE.parent / "common"
sys.path.insert(0, str(COMMON_DIR))

from evaluator_common import VariantConfig, run_evaluator

# Variant-specific configuration
CONFIG = VariantConfig(
    num_particles=10000,
    num_iterations=5,
    space_size=100.0,
    num_runs=3,
    min_speedup=1.0,   # 1x speedup = 0 points
    max_speedup=5.5,   # 5.5x speedup = 100 points (Cursor with Opus 4.5 can achieve 4.55x with ~5 iterations)
)

DEFAULT_SPEC = HERE / "resources" / "submission_spec.json"

if __name__ == "__main__":
    run_evaluator(CONFIG, DEFAULT_SPEC)
