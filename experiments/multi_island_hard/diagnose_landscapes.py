#!/usr/bin/env python3
"""Operator-side diagnostics for the high-dimensional NK ladder.

Exact enumeration is impossible at N=128. We therefore use a deterministic
Monte Carlo sample, one-bit autocorrelation, sampled local-maximum rate, and
multi-start greedy ascent. These numbers characterize difficulty; they are not
hidden answers and are kept outside the agent-visible run until collection is
complete.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "tasks/institutional_landscape/taskdata"


def fitness(candidate: str, *, k: int, seed: str) -> float:
    n = len(candidate)
    total = 0.0
    for index in range(n):
        pattern = "".join(candidate[(index + offset) % n] for offset in range(k + 1))
        digest = hashlib.sha256(f"{seed}:{index}:{pattern}".encode()).digest()
        total += int.from_bytes(digest[:8], "big") / 2**64
    return total / n


def random_candidate(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("01") for _ in range(n))


def flip(candidate: str, index: int) -> str:
    bit = "1" if candidate[index] == "0" else "0"
    return candidate[:index] + bit + candidate[index + 1 :]


def greedy_ascent(candidate: str, *, k: int, seed: str) -> tuple[str, int]:
    current = candidate
    current_score = fitness(current, k=k, seed=seed)
    steps = 0
    while True:
        best = current
        best_score = current_score
        for index in range(len(current)):
            trial = flip(current, index)
            score = fitness(trial, k=k, seed=seed)
            if score > best_score:
                best, best_score = trial, score
        if best == current:
            return current, steps
        current, current_score = best, best_score
        steps += 1


def diagnose(path: Path, *, samples: int, starts: int) -> dict[str, object]:
    config = json.loads(path.read_text())
    n, k, seed = int(config["n"]), int(config["k"]), str(config["seed"])
    rng = random.Random(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big"))
    candidates = [random_candidate(rng, n) for _ in range(samples)]
    scores = [fitness(candidate, k=k, seed=seed) for candidate in candidates]
    neighbor_pairs = []
    local_maxima = 0
    for candidate, score in zip(candidates, scores, strict=True):
        neighbor_scores = [fitness(flip(candidate, i), k=k, seed=seed) for i in range(n)]
        neighbor_pairs.extend(zip([score] * n, neighbor_scores, strict=True))
        if score > max(neighbor_scores):
            local_maxima += 1
    mean_x = sum(x for x, _ in neighbor_pairs) / len(neighbor_pairs)
    mean_y = sum(y for _, y in neighbor_pairs) / len(neighbor_pairs)
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in neighbor_pairs)
    variance_x = sum((x - mean_x) ** 2 for x, _ in neighbor_pairs)
    variance_y = sum((y - mean_y) ** 2 for _, y in neighbor_pairs)
    autocorrelation = covariance / (variance_x * variance_y) ** 0.5

    maxima: dict[str, int] = {}
    ascent_steps: list[int] = []
    for _ in range(starts):
        maximum, steps = greedy_ascent(random_candidate(rng, n), k=k, seed=seed)
        maxima[maximum] = maxima.get(maximum, 0) + 1
        ascent_steps.append(steps)
    maxima_scores = [fitness(candidate, k=k, seed=seed) for candidate in maxima]
    return {
        "config": path.name,
        "n": n,
        "k": k,
        "seed_sha256": hashlib.sha256(seed.encode()).hexdigest(),
        "sample_count": samples,
        "sample_mean": sum(scores) / len(scores),
        "sample_sd": (sum((x - sum(scores) / len(scores)) ** 2 for x in scores) / len(scores)) ** 0.5,
        "seed_candidate_fitness": fitness("0" * n, k=k, seed=seed),
        "sample_best_fitness": max(scores),
        "one_bit_autocorrelation": autocorrelation,
        "sample_local_max_rate": local_maxima / samples,
        "greedy_start_count": starts,
        "greedy_unique_maxima": len(maxima),
        "greedy_best_fitness": max(maxima_scores),
        "greedy_mean_steps": sum(ascent_steps) / len(ascent_steps),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--starts", type=int, default=250)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {
        "schema_version": 1,
        "method": "Monte Carlo + sampled one-bit neighborhood + greedy ascent",
        "samples": args.samples,
        "starts": args.starts,
        "landscapes": [
            diagnose(ROOT / name, samples=args.samples, starts=args.starts)
            for name in (
                "smooth128.json",
                "rugged128_k4.json",
                "rugged128_k12.json",
                "rugged128_k24.json",
            )
        ],
    }
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
