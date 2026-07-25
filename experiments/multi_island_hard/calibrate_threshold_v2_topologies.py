#!/usr/bin/env python3
"""Calibrate whether replicated NK landscapes can expose an island effect.

This is a task-sensitivity check, not an agent-performance forecast.  It runs
one frozen, conventional two-point-crossover genetic algorithm with identical
starts and evaluation budgets under panmictic, partitioned, and island-model
selection.  Calibration seeds are never reused in the LLM confirmation cells.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments.multi_island_hard.run_threshold_v2 import BUDGETS, migration_every

ROOT = Path(__file__).resolve().parent
CALIBRATION_LANDSCAPES = ROOT / "threshold_v2_calibration_landscapes.json"
DEFAULT_OUTPUT = ROOT / "threshold_v2_topology_calibration.json"
CONDITIONS = ("global_8", "multi_island_2", "multi_island_4")
BASE_AGENT_IDS = (
    "captain-nemo",
    "captain-ahab",
    "jack-sparrow",
    "davy-jones",
    "long-john-silver",
    "sinbad-the-sailor",
    "horatio-hornblower",
    "jack-aubrey",
)
RANDOM_SAMPLES = 512
RUGGED_EFFECT_FLOOR_Z = 0.25
INTERACTION_FLOOR_Z = 0.50


@dataclass(frozen=True)
class Individual:
    candidate: str
    score: float


def initial_candidate(agent_id: str, n: int) -> str:
    digest = hashlib.sha256(f"coral-threshold-v2:{agent_id}".encode()).digest()
    bits = "".join(f"{byte:08b}" for byte in digest)
    while len(bits) < n:
        digest = hashlib.sha256(digest).digest()
        bits += "".join(f"{byte:08b}" for byte in digest)
    return bits[:n]


def nk_fitness(candidate: str, *, k: int, seed: str) -> float:
    n = len(candidate)
    wrapped = candidate + candidate[:k]
    total = 0.0
    for index in range(n):
        pattern = wrapped[index : index + k + 1]
        digest = hashlib.sha256(f"{seed}:{index}:{pattern}".encode()).digest()
        total += int.from_bytes(digest[:8], "big") / 2**64
    return total / n


def mean_hamming(population: list[Individual]) -> float:
    distances = [
        sum(left != right for left, right in zip(a.candidate, b.candidate, strict=True))
        / len(a.candidate)
        for index, a in enumerate(population)
        for b in population[index + 1 :]
    ]
    return statistics.fmean(distances) if distances else 0.0


def _groups(condition: str) -> tuple[tuple[int, ...], ...]:
    if condition == "global_8":
        return (tuple(range(8)),)
    if condition == "multi_island_2":
        return (tuple(range(0, 8, 2)), tuple(range(1, 8, 2)))
    if condition == "multi_island_4":
        return tuple(tuple(range(offset, 8, 4)) for offset in range(4))
    raise ValueError(f"unknown condition {condition!r}")


def _tournament(
    population: list[Individual],
    group: tuple[int, ...],
    rng: random.Random,
) -> Individual:
    left, right = rng.sample(group, 2)
    return max((population[left], population[right]), key=lambda item: item.score)


def _offspring(
    population: list[Individual],
    group: tuple[int, ...],
    *,
    k: int,
    seed: str,
    rng: random.Random,
) -> Individual:
    first = _tournament(population, group, rng)
    second = _tournament(population, group, rng)
    n = len(first.candidate)
    left, right = sorted(rng.sample(range(1, n), 2))
    bits = list(
        first.candidate[:left]
        + second.candidate[left:right]
        + first.candidate[right:]
    )
    flips = [index for index in range(n) if rng.random() < 1 / n]
    if not flips:
        flips = [rng.randrange(n)]
    for index in flips:
        bits[index] = "1" if bits[index] == "0" else "0"
    candidate = "".join(bits)
    return Individual(candidate, nk_fitness(candidate, k=k, seed=seed))


def _copy_best_migrants(population: list[Individual], groups: tuple[tuple[int, ...], ...]) -> None:
    champions = [
        max((population[index] for index in group), key=lambda item: item.score)
        for group in groups
    ]
    for destination, group in enumerate(groups):
        worst = min(group, key=lambda index: population[index].score)
        population[worst] = champions[(destination - 1) % len(groups)]


def simulate(
    *,
    n: int,
    k: int,
    seed: str,
    condition: str,
    budget: int,
    policy_seed: int,
) -> dict[str, Any]:
    if budget not in BUDGETS or budget < len(BASE_AGENT_IDS):
        raise ValueError("simulation budget is not registered")
    rng = random.Random(policy_seed)
    population = [
        Individual(candidate, nk_fitness(candidate, k=k, seed=seed))
        for candidate in (initial_candidate(agent_id, n) for agent_id in BASE_AGENT_IDS)
    ]
    groups = _groups(condition)
    evaluations = len(population)
    every = migration_every(budget)
    next_migration = every
    migrations = 0
    while evaluations < budget:
        children: dict[int, Individual] = {}
        for group in groups:
            for slot in group:
                children[slot] = _offspring(
                    population,
                    group,
                    k=k,
                    seed=seed,
                    rng=rng,
                )
                evaluations += 1
                if evaluations == budget:
                    break
            if evaluations == budget:
                break
        for group in groups:
            pool = [population[index] for index in group]
            pool.extend(children[index] for index in group if index in children)
            survivors = sorted(
                pool,
                key=lambda item: (-item.score, item.candidate),
            )[: len(group)]
            for slot, survivor in zip(group, survivors, strict=True):
                population[slot] = survivor
        if condition.startswith("multi_island_") and evaluations >= next_migration:
            _copy_best_migrants(population, groups)
            migrations += 1
            next_migration += every
    return {
        "best_score": max(item.score for item in population),
        "final_diversity": mean_hamming(population),
        "migration_cycles": migrations,
    }


def _work_item(item: tuple[int, int, str, str, int, int]) -> dict[str, Any]:
    n, k, seed, condition, budget, policy_seed = item
    metrics = simulate(
        n=n,
        k=k,
        seed=seed,
        condition=condition,
        budget=budget,
        policy_seed=policy_seed,
    )
    return {
        "k": k,
        "seed_sha256": hashlib.sha256(seed.encode()).hexdigest(),
        "condition": condition,
        "budget": budget,
        "policy_seed": policy_seed,
        **metrics,
    }


def random_reference(n: int, k: int, seed: str) -> dict[str, float]:
    rng_seed = int.from_bytes(
        hashlib.sha256(f"threshold-v2-policy-reference:{k}:{seed}".encode()).digest()[:8],
        "big",
    )
    rng = random.Random(rng_seed)
    scores = [
        nk_fitness(f"{rng.getrandbits(n):0{n}b}", k=k, seed=seed)
        for _ in range(RANDOM_SAMPLES)
    ]
    return {
        "random_mean": statistics.fmean(scores),
        "random_sd": statistics.pstdev(scores),
    }


def bootstrap_interval(values: list[float], label: str) -> tuple[float, float]:
    rng_seed = int.from_bytes(hashlib.sha256(label.encode()).digest()[:8], "big")
    rng = random.Random(rng_seed)
    samples = sorted(
        statistics.fmean(rng.choice(values) for _ in values)
        for _ in range(20_000)
    )
    return samples[500], samples[19_500]


def summarize(
    rows: list[dict[str, Any]],
    references: dict[tuple[int, str], dict[str, float]],
) -> list[dict[str, Any]]:
    indexed = {
        (
            int(row["k"]),
            str(row["seed_sha256"]),
            int(row["budget"]),
            int(row["policy_seed"]),
            str(row["condition"]),
        ): row
        for row in rows
    }
    output = []
    for k in sorted({int(row["k"]) for row in rows}):
        for budget in BUDGETS:
            for treatment in ("multi_island_2", "multi_island_4"):
                raw_effects: list[float] = []
                z_effects: list[float] = []
                diversity_effects: list[float] = []
                keys = sorted(
                    {
                        (str(row["seed_sha256"]), int(row["policy_seed"]))
                        for row in rows
                        if int(row["k"]) == k and int(row["budget"]) == budget
                    }
                )
                for seed_hash, policy_seed in keys:
                    multi = indexed[(k, seed_hash, budget, policy_seed, treatment)]
                    global_row = indexed[(k, seed_hash, budget, policy_seed, "global_8")]
                    raw = float(multi["best_score"]) - float(global_row["best_score"])
                    reference = references[(k, seed_hash)]
                    raw_effects.append(raw)
                    z_effects.append(raw / reference["random_sd"])
                    diversity_effects.append(
                        float(multi["final_diversity"])
                        - float(global_row["final_diversity"])
                    )
                label = f"policy:{k}:{budget}:{treatment}"
                z_low, z_high = bootstrap_interval(z_effects, f"{label}:z")
                raw_low, raw_high = bootstrap_interval(raw_effects, f"{label}:raw")
                output.append(
                    {
                        "k": k,
                        "budget": budget,
                        "contrast": f"{treatment}_minus_global_8",
                        "paired_policy_runs": len(z_effects),
                        "multi_minus_global_score": statistics.fmean(raw_effects),
                        "multi_minus_global_score_ci_low": raw_low,
                        "multi_minus_global_score_ci_high": raw_high,
                        "multi_minus_global_random_z": statistics.fmean(z_effects),
                        "multi_minus_global_random_z_ci_low": z_low,
                        "multi_minus_global_random_z_ci_high": z_high,
                        "multi_win_rate": sum(value > 0 for value in raw_effects)
                        / len(raw_effects),
                        "multi_minus_global_diversity": statistics.fmean(diversity_effects),
                    }
                )
    return output


def add_sensitivity_flags(summary: list[dict[str, Any]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for row in summary:
        k = int(row["k"])
        if k == 0 or row["contrast"] != "multi_island_4_minus_global_8":
            row["task_sensitivity_passes"] = False
            continue
        smooth = next(
            item
            for item in summary
            if int(item["k"]) == 0
            and int(item["budget"]) == int(row["budget"])
            and item["contrast"] == "multi_island_4_minus_global_8"
        )
        interaction = float(row["multi_minus_global_random_z"]) - float(
            smooth["multi_minus_global_random_z"]
        )
        # The two effects share policy seeds but not per-row bootstrap samples;
        # the calibration flag is deliberately descriptive.  Confirmation uses
        # paired landscape-level inference in analyze_threshold_v2.py.
        passes = (
            float(row["multi_minus_global_random_z"]) >= RUGGED_EFFECT_FLOOR_Z
            and float(row["multi_minus_global_random_z_ci_low"]) > 0
            and interaction >= INTERACTION_FLOOR_Z
        )
        row["rugged_minus_smooth_random_z"] = interaction
        row["task_sensitivity_passes"] = passes
        if passes:
            candidates.append({"k": k, "budget": int(row["budget"])})
    return {
        "rugged_effect_floor_random_z": RUGGED_EFFECT_FLOOR_Z,
        "rugged_minus_smooth_floor_random_z": INTERACTION_FLOOR_Z,
        "passing_k_budget_cells": candidates,
        "calibration_supports_llm_threshold_study": bool(candidates),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy-repetitions", type=int, default=8)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.policy_repetitions < 1 or args.workers < 1:
        raise SystemExit("policy repetitions and workers must be positive")
    landscape_data = json.loads(CALIBRATION_LANDSCAPES.read_text())
    n = int(landscape_data["n"])
    seeds = [str(seed) for seed in landscape_data["seeds"]]
    k_values = [int(k) for k in landscape_data["k_values"]]
    references = {
        (k, hashlib.sha256(seed.encode()).hexdigest()): random_reference(n, k, seed)
        for k in k_values
        for seed in seeds
    }
    items = [
        (n, k, seed, condition, budget, policy_seed)
        for k in k_values
        for seed_index, seed in enumerate(seeds)
        for condition in CONDITIONS
        for budget in BUDGETS
        for repetition in range(args.policy_repetitions)
        for policy_seed in [seed_index * 10_000 + repetition]
    ]
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(_work_item, items, chunksize=4))
    summary = summarize(rows, references)
    decision = add_sensitivity_flags(summary)
    payload = {
        "schema_version": 1,
        "method": "frozen two-point-crossover tournament GA task-sensitivity check",
        "interpretation": "positive control for landscape sensitivity, not an LLM forecast",
        "calibration_seed_count": len(seeds),
        "policy_repetitions": args.policy_repetitions,
        "random_reference_samples": RANDOM_SAMPLES,
        "budgets": list(BUDGETS),
        "migration_cadence": "budget / 4, clipped to [64, 512]",
        "decision": decision,
        "summary": summary,
    }
    rendered = json.dumps(payload, indent=2) + "\n"
    args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
