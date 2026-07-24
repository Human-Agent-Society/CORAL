#!/usr/bin/env python3
"""Exhaustively characterize the frozen N=20 NK landscapes operator-side."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

DEFAULT_TASKDATA = Path(__file__).parent / "tasks/institutional_landscape/taskdata"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--taskdata", type=Path, default=DEFAULT_TASKDATA)
    return parser.parse_args()


def contribution_tables(n: int, k: int, seed: str) -> np.ndarray:
    tables = np.empty((n, 1 << (k + 1)), dtype=np.float64)
    for index in range(n):
        for pattern_value in range(1 << (k + 1)):
            pattern = format(pattern_value, f"0{k + 1}b")
            digest = hashlib.sha256(f"{seed}:{index}:{pattern}".encode()).digest()
            tables[index, pattern_value] = int.from_bytes(digest[:8], "big") / 2**64
    return tables


def diagnose(config_path: Path) -> dict[str, object]:
    raw = config_path.read_bytes()
    config = json.loads(raw)
    n, k, seed = int(config["n"]), int(config["k"]), str(config["seed"])
    if n != 20:
        raise ValueError(f"exhaustive diagnostic expects N=20, got {n}")

    states = np.arange(1 << n, dtype=np.uint32)
    scores = np.zeros(1 << n, dtype=np.float64)
    tables = contribution_tables(n, k, seed)
    for index in range(n):
        patterns = np.zeros(1 << n, dtype=np.uint8)
        for offset in range(k + 1):
            bit_index = (index + offset) % n
            patterns = (patterns << 1) | ((states >> (n - 1 - bit_index)) & 1)
        scores += tables[index, patterns]
    scores /= n

    local_maxima = np.ones(1 << n, dtype=np.bool_)
    for bit_index in range(n):
        neighbours = states ^ np.uint32(1 << (n - 1 - bit_index))
        local_maxima &= scores > scores[neighbours]

    optimum = int(np.argmax(scores))
    return {
        "config": config_path.name,
        "config_sha256": hashlib.sha256(raw).hexdigest(),
        "n": n,
        "k": k,
        "candidate_count": 1 << n,
        "one_bit_local_maxima": int(np.count_nonzero(local_maxima)),
        "global_optimum_fitness": float(scores[optimum]),
        "global_optimum_candidate_sha256": hashlib.sha256(
            format(optimum, f"0{n}b").encode()
        ).hexdigest(),
        "seed_candidate_fitness": float(scores[0]),
        "fitness_mean": float(np.mean(scores)),
        "fitness_sd": float(np.std(scores)),
    }


def main() -> int:
    args = parse_args()
    report = {
        "schema_version": 1,
        "landscapes": [diagnose(args.taskdata / name) for name in ("smooth.json", "rugged.json")],
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
