#!/usr/bin/env python3
"""Freeze N=256 random baselines and greedy reference scores."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments.multi_island_hard.diagnose_threshold_v2 import diagnose_seed

ROOT = Path(__file__).resolve().parent
TASKDATA = ROOT / "tasks/institutional_landscape/taskdata"
TASKS = {
    "smooth256_rep_v3": "smooth256_replicated_v3.json",
    "rugged256_k32_rep_v3": "rugged256_k32_replicated_v3.json",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=1024)
    parser.add_argument("--starts", type=int, default=64)
    parser.add_argument("--output", type=Path, default=ROOT / "threshold_v3_diagnostics.json")
    args = parser.parse_args()
    rows = []
    for task, filename in TASKS.items():
        config = json.loads((TASKDATA / filename).read_text())
        for seed_index, seed in enumerate(config["seeds"]):
            rows.append(
                diagnose_seed(
                    task,
                    seed_index,
                    str(seed),
                    n=int(config["n"]),
                    k=int(config["k"]),
                    samples=args.samples,
                    starts=args.starts,
                )
            )
    payload = {
        "schema_version": 3,
        "method": "paired-seed random baseline plus deterministic multi-start greedy ascent",
        "random_samples": args.samples,
        "greedy_starts": args.starts,
        "landscapes": rows,
    }
    rendered = json.dumps(payload, indent=2) + "\n"
    args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
