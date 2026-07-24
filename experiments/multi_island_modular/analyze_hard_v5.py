#!/usr/bin/env python3
"""Audit the v5 high-dimensional modular threshold matrix.

The integrity and provenance logic is shared with the audited v4 analyzer;
all package-specific constants and paths are replaced with the v5 grader.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
V5_GRADER_SRC = ROOT / "tasks/hard_active_modular_landscape_v5/grader/src"
sys.path.insert(0, str(V5_GRADER_SRC))
from hard_active_modular_landscape_v5_grader.grader import (  # noqa: E402
    BLOCKS,
    CODEBOOK_SIZE,
    TOTAL_WIDTH,
    WIDTH,
    active_score,
    rugged_target,
    target_bits,
)

from experiments.multi_island_modular import analyze_hard_v4 as base  # noqa: E402

base.ROOT = ROOT
base.TASKDATA = ROOT / "tasks/hard_active_modular_landscape_v5/taskdata/hard_v5_seed_bundle.json"
base.SEED_BUNDLE_FILENAME = "hard_v5_seed_bundle.json"
base.SEED_SCHEMA_VERSION = 3
base.ROLE_PROTOCOL_FILENAME = "hard_v5_eval_protocol.md"
base.MIN_MODULE_COVERAGE = 12
base.MIN_ISLAND_COVERAGE = 6
base.MIN_EXACT_SIGNAL = 1
# Keep the analyzer's launch identity in lockstep with run_hard_v5: migration
# must not happen before agents have had room to make module-level progress.
base.MIGRATION_DIVISOR = 4
base.MIGRATION_MIN = 64
base.MIGRATION_MAX = 256
base.REMIGRATION_COOLDOWN = 64
base.ANALYZER_LABEL = "Hard v5"
base.__doc__ = __doc__
base.TOPOLOGY_AGENT_COUNTS = {
    "global": "4",
    "global_8": "8",
    "partition": "8",
    "multi_island": "8",
}
base.TASKS = ("smooth_hard_v5", "rugged_hard_v5")
base.REPETITIONS = 8
base.DEFAULT_BUDGETS = (256, 512, 1024, 1536, 4096, 8192, 16384, 24576)
base.BLOCKS = BLOCKS
base.WIDTH = WIDTH
base.CODEBOOK_SIZE = CODEBOOK_SIZE
base.TOTAL_WIDTH = TOTAL_WIDTH
base.active_score = active_score
base.rugged_target = rugged_target
base.target_bits = target_bits


if __name__ == "__main__":
    raise SystemExit(base.main())
