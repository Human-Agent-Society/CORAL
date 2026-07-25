#!/usr/bin/env python3
"""Freeze held-out N=512 baselines only after v4 selects K and budget."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments.multi_island_hard.diagnose_threshold_v2 import diagnose_seed
from experiments.multi_island_hard.run_threshold_v4 import (
    RUGGED_TASKS,
    SMOOTH_TASK,
    registered_selection,
)

ROOT = Path(__file__).resolve().parent
TASKDATA = ROOT / "tasks/institutional_landscape/taskdata"
DEFAULT_OUTPUT = ROOT / "threshold_v4_diagnostics.json"


def selected_tasks() -> dict[str, str]:
    selection = registered_selection()
    k = selection["k"]
    return {
        SMOOTH_TASK: "smooth512_replicated_v4.json",
        RUGGED_TASKS[k]: f"rugged512_k{k}_replicated_v4.json",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=1024)
    parser.add_argument("--starts", type=int, default=32)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.samples < 128 or args.starts < 8:
        raise SystemExit("v4 diagnostics require at least 128 samples and 8 greedy starts")
    selection = registered_selection()
    rows = []
    for task, filename in selected_tasks().items():
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
        "schema_version": 4,
        "method": "paired held-out random baseline plus deterministic multi-start greedy ascent",
        "selected_k": selection["k"],
        "selected_budget": selection["budget"],
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
