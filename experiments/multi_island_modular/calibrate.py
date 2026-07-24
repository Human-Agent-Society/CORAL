#!/usr/bin/env python3
"""Operator-side calibration for the modular landscape pair.

This script knows the frozen seed, so it is never used inside an agent run.
It establishes the exact optimum, trap baseline, random score moments, and a
simple module-discovery curve before a topology result is interpreted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASKDATA = ROOT / "tasks/modular_landscape/taskdata"


def target_bits(seed: str, block: int, width: int) -> str:
    bits = ""
    counter = 0
    while len(bits) < width:
        digest = hashlib.sha256(f"{seed}:target:{block}:{counter}".encode()).digest()
        bits += "".join(f"{byte:08b}" for byte in digest)
        counter += 1
    value = bits[:width]
    if value.count("1") < 2:
        value = "11" + value[2:]
    return value


def module_score(bits: str, target: str, mode: str) -> float:
    if mode == "smooth":
        return 0.1 + 0.9 * sum(a == b for a, b in zip(bits, target, strict=True)) / len(target)
    if bits == target:
        return 1.0
    if bits == "0" * len(target):
        return 0.72
    return 0.55 - 0.20 * bits.count("1") / len(target)


def score(candidate: str, *, mode: str, seed: str, blocks: int, width: int) -> tuple[float, int, int]:
    exact: list[bool] = []
    scores: list[float] = []
    for block in range(blocks):
        part = candidate[block * width : (block + 1) * width]
        target = target_bits(seed, block, width)
        scores.append(module_score(part, target, mode))
        exact.append(part == target)
    pairs = sum(left and right for left, right in zip(exact, exact[1:]))
    bridge = pairs / max(1, blocks - 1)
    total = (sum(scores) + 0.35 * bridge) / (blocks + 0.35)
    return total, sum(exact), pairs


def random_candidate(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("01") for _ in range(n))


def module_discovery_curve(
    *, mode: str, seed: str, blocks: int, width: int, budgets: list[int], samples: int
) -> list[dict[str, float]]:
    """Estimate how many exact modules random block proposals can discover."""
    n = blocks * width
    targets = [target_bits(seed, b, width) for b in range(blocks)]
    rows: list[dict[str, float]] = []
    for budget in budgets:
        discovered: list[int] = []
        totals: list[float] = []
        for sample in range(samples):
            rng = random.Random(
                int.from_bytes(hashlib.sha256(f"{seed}:{mode}:{budget}:{sample}".encode()).digest()[:8], "big")
            )
            candidate = ["0"] * n
            for _ in range(budget):
                block = rng.randrange(blocks)
                start = block * width
                proposal = random_candidate(rng, width)
                current = "".join(candidate[start : start + width])
                target = targets[block]
                if module_score(proposal, target, mode) >= module_score(current, target, mode):
                    candidate[start : start + width] = list(proposal)
            value, exact, pairs = score("".join(candidate), mode=mode, seed=seed, blocks=blocks, width=width)
            # Keep this assertion close to the simulator: target derivation and
            # scorer must agree before any LLM result is trusted.
            expected = sum(
                "".join(candidate[b * width : (b + 1) * width]) == targets[b]
                for b in range(blocks)
            )
            if exact != expected:
                raise AssertionError("module discovery scorer mismatch")
            discovered.append(exact)
            totals.append(value)
        rows.append(
            {
                "budget": budget,
                "mean_exact_blocks": statistics.fmean(discovered),
                "sd_exact_blocks": statistics.stdev(discovered) if len(discovered) > 1 else 0.0,
                "mean_total": statistics.fmean(totals),
            }
        )
    return rows


def calibrate(path: Path, budgets: list[int], samples: int) -> dict[str, object]:
    config = json.loads(path.read_text())
    mode = str(config["mode"])
    seed = str(config["seed"])
    blocks = int(config["blocks"])
    width = int(config["block_width"])
    n = blocks * width
    zero = "0" * n
    optimum = "".join(target_bits(seed, block, width) for block in range(blocks))
    rng = random.Random(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big"))
    random_scores = [score(random_candidate(rng, n), mode=mode, seed=seed, blocks=blocks, width=width)[0] for _ in range(samples)]
    zero_score, zero_exact, zero_pairs = score(zero, mode=mode, seed=seed, blocks=blocks, width=width)
    optimum_score, optimum_exact, optimum_pairs = score(optimum, mode=mode, seed=seed, blocks=blocks, width=width)
    return {
        "schema_version": 1,
        "task": path.stem,
        "mode": mode,
        "blocks": blocks,
        "block_width": width,
        "n": n,
        "seed_sha256": hashlib.sha256(seed.encode()).hexdigest(),
        "zero_score": zero_score,
        "zero_exact_blocks": zero_exact,
        "zero_exact_pairs": zero_pairs,
        "exact_optimum_score": optimum_score,
        "exact_optimum_blocks": optimum_exact,
        "exact_optimum_pairs": optimum_pairs,
        "random_mean": statistics.fmean(random_scores),
        "random_sd": statistics.stdev(random_scores) if len(random_scores) > 1 else 0.0,
        "random_best": max(random_scores),
        "module_discovery_curve": module_discovery_curve(
            mode=mode, seed=seed, blocks=blocks, width=width, budgets=budgets, samples=samples
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budgets", type=int, nargs="+", default=[64, 128, 256, 512])
    parser.add_argument("--samples", type=int, default=250)
    parser.add_argument("--output", type=Path, default=ROOT / "calibration.json")
    args = parser.parse_args()
    report = {
        "schema_version": 1,
        "method": "exact target/trap audit + random block-proposal calibration",
        "budgets": args.budgets,
        "samples": args.samples,
        "tasks": [
            calibrate(TASKDATA / name, args.budgets, args.samples)
            for name in (
                "smooth_modular128.json",
                "rugged_modular128.json",
                "smooth_modular192.json",
                "rugged_modular192.json",
            )
        ],
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
