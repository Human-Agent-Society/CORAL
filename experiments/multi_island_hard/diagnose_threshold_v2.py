#!/usr/bin/env python3
"""Freeze replicated N=128 random baselines and greedy reference scores."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
TASKDATA = ROOT / "tasks/institutional_landscape/taskdata"
TASKS = {
    "smooth128_rep_v2": "smooth128_replicated_v2.json",
    "rugged128_k12_rep_v2": "rugged128_k12_replicated_v2.json",
}


def contribution(candidate: str, index: int, *, k: int, seed: str) -> float:
    n = len(candidate)
    pattern = "".join(candidate[(index + offset) % n] for offset in range(k + 1))
    digest = hashlib.sha256(f"{seed}:{index}:{pattern}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def contributions(candidate: str, *, k: int, seed: str) -> list[float]:
    return [contribution(candidate, index, k=k, seed=seed) for index in range(len(candidate))]


def random_candidate(rng: random.Random, n: int) -> str:
    return f"{rng.getrandbits(n):0{n}b}"


def flip(candidate: str, index: int) -> str:
    bit = "1" if candidate[index] == "0" else "0"
    return candidate[:index] + bit + candidate[index + 1 :]


def affected_indices(index: int, n: int, k: int) -> tuple[int, ...]:
    return tuple((index - offset) % n for offset in range(k + 1))


def greedy_ascent(candidate: str, *, k: int, seed: str) -> tuple[str, float, int]:
    n = len(candidate)
    current = candidate
    current_values = contributions(current, k=k, seed=seed)
    current_total = sum(current_values)
    steps = 0
    while True:
        best_index: int | None = None
        best_total = current_total
        best_updates: dict[int, float] = {}
        for bit in range(n):
            trial = flip(current, bit)
            updates = {
                component: contribution(trial, component, k=k, seed=seed)
                for component in affected_indices(bit, n, k)
            }
            total = current_total + sum(
                value - current_values[component] for component, value in updates.items()
            )
            if total > best_total:
                best_index = bit
                best_total = total
                best_updates = updates
        if best_index is None:
            return current, current_total / n, steps
        current = flip(current, best_index)
        current_total = best_total
        for component, value in best_updates.items():
            current_values[component] = value
        steps += 1


def smooth_optimum(n: int, seed: str) -> tuple[str, float]:
    bits = []
    values = []
    for index in range(n):
        zero = contribution("0" * n, index, k=0, seed=seed)
        candidate = "0" * index + "1" + "0" * (n - index - 1)
        one = contribution(candidate, index, k=0, seed=seed)
        if one > zero:
            bits.append("1")
            values.append(one)
        else:
            bits.append("0")
            values.append(zero)
    return "".join(bits), statistics.fmean(values)


def diagnose_seed(
    task: str,
    seed_index: int,
    seed: str,
    *,
    n: int,
    k: int,
    samples: int,
    starts: int,
) -> dict[str, Any]:
    rng_seed = int.from_bytes(
        hashlib.sha256(f"threshold-v2-diagnostics:{task}:{seed}".encode()).digest()[:8],
        "big",
    )
    rng = random.Random(rng_seed)
    candidates = [random_candidate(rng, n) for _ in range(samples)]
    scores = [statistics.fmean(contributions(item, k=k, seed=seed)) for item in candidates]
    neighbor_scores = [
        statistics.fmean(contributions(flip(item, rng.randrange(n)), k=k, seed=seed))
        for item in candidates
    ]
    mean = statistics.fmean(scores)
    neighbor_mean = statistics.fmean(neighbor_scores)
    covariance = sum(
        (left - mean) * (right - neighbor_mean)
        for left, right in zip(scores, neighbor_scores, strict=True)
    )
    variance_left = sum((value - mean) ** 2 for value in scores)
    variance_right = sum((value - neighbor_mean) ** 2 for value in neighbor_scores)
    autocorrelation = covariance / (variance_left * variance_right) ** 0.5

    maxima: dict[str, float] = {}
    steps: list[int] = []
    for _ in range(starts):
        maximum, score, count = greedy_ascent(random_candidate(rng, n), k=k, seed=seed)
        maxima[maximum] = score
        steps.append(count)
    greedy_best = max(maxima.values())
    exact_reference = k == 0
    if exact_reference:
        optimum, optimum_score = smooth_optimum(n, seed)
        if abs(greedy_best - optimum_score) > 1e-12 or set(maxima) != {optimum}:
            raise AssertionError("smooth greedy calibration did not recover its unique optimum")
        greedy_best = optimum_score
    return {
        "task": task,
        "seed_index": seed_index,
        "seed_sha256": hashlib.sha256(seed.encode()).hexdigest(),
        "n": n,
        "k": k,
        "random_sample_count": samples,
        "random_mean": mean,
        "random_sd": statistics.pstdev(scores),
        "random_best": max(scores),
        "zero_candidate_score": statistics.fmean(contributions("0" * n, k=k, seed=seed)),
        "one_bit_autocorrelation": autocorrelation,
        "greedy_start_count": starts,
        "greedy_unique_maxima": len(maxima),
        "greedy_reference_score": greedy_best,
        "greedy_mean_steps": statistics.fmean(steps),
        "reference_is_exact": exact_reference,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=512)
    parser.add_argument("--starts", type=int, default=64)
    parser.add_argument("--output", type=Path, default=ROOT / "threshold_v2_diagnostics.json")
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
        "schema_version": 2,
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
