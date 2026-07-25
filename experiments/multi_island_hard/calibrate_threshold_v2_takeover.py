#!/usr/bin/env python3
"""Calibrate the diversity-preservation mechanism under champion takeover.

Unlike ``calibrate_threshold_v2_topologies.py``'s conventional population GA,
this frozen policy models the failure mode claimed in the blog: after every
generation, everyone who can see the same attempts adopts the best visible
lineage.  Global search therefore follows one lineage, while two or four
islands retain independent champions until selective migration exposes them.

This is a mechanism-positive sensitivity check, not evidence about LLM agents.
The LLM analyzer reports duplicate rates and diversity without conditioning on
them, so the takeover assumption can be falsified by the real runs.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import random
import statistics
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import calibrate_threshold_v2_topologies as common
from experiments.multi_island_hard.run_threshold_v2 import BUDGETS, migration_every

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "threshold_v2_takeover_calibration.json"
CONDITIONS = {
    "global_8": 1,
    "partition_4": 4,
    "multi_island_2": 2,
    "multi_island_4": 4,
}
RUGGED_EFFECT_FLOOR_Z = 0.25
INTERACTION_FLOOR_Z = 0.25


def groups_for(island_count: int) -> tuple[tuple[int, ...], ...]:
    if 8 % island_count:
        raise ValueError("island count must divide the fixed eight-agent roster")
    return tuple(tuple(range(offset, 8, island_count)) for offset in range(island_count))


def mutate(
    incumbent: common.Individual,
    *,
    k: int,
    seed: str,
    rng: random.Random,
) -> common.Individual:
    bits = list(incumbent.candidate)
    n = len(bits)
    flips = [index for index in range(n) if rng.random() < 1 / n]
    if not flips:
        flips = [rng.randrange(n)]
    for index in flips:
        bits[index] = "1" if bits[index] == "0" else "0"
    candidate = "".join(bits)
    return common.Individual(candidate, common.nk_fitness(candidate, k=k, seed=seed))


def expose_cyclic_migrants(
    population: list[common.Individual],
    groups: tuple[tuple[int, ...], ...],
) -> None:
    champions = [
        max((population[index] for index in group), key=lambda item: item.score)
        for group in groups
    ]
    for destination, group in enumerate(groups):
        population[group[-1]] = champions[(destination - 1) % len(groups)]


def simulate(
    *,
    n: int,
    k: int,
    seed: str,
    condition: str,
    budget: int,
    policy_seed: int,
) -> dict[str, Any]:
    island_count = CONDITIONS[condition]
    rng = random.Random(policy_seed)
    population = [
        common.Individual(candidate, common.nk_fitness(candidate, k=k, seed=seed))
        for candidate in (
            common.initial_candidate(agent_id, n) for agent_id in common.BASE_AGENT_IDS
        )
    ]
    groups = groups_for(island_count)
    evaluations = len(population)
    every = migration_every(budget)
    next_migration = every
    migrations = 0
    while evaluations < budget:
        children: dict[int, common.Individual] = {}
        for group in groups:
            champion = max(
                (population[index] for index in group),
                key=lambda item: item.score,
            )
            for slot in group:
                children[slot] = mutate(champion, k=k, seed=seed, rng=rng)
                evaluations += 1
                if evaluations == budget:
                    break
            if evaluations == budget:
                break
        for group in groups:
            pool = [population[index] for index in group]
            pool.extend(children[index] for index in group if index in children)
            champion = max(pool, key=lambda item: (item.score, item.candidate))
            for slot in group:
                population[slot] = champion
        if condition.startswith("multi_island_") and evaluations >= next_migration:
            expose_cyclic_migrants(population, groups)
            migrations += 1
            next_migration += every
    return {
        "best_score": max(item.score for item in population),
        "final_diversity": common.mean_hamming(population),
        "migration_cycles": migrations,
    }


def _work_item(item: tuple[int, int, str, str, int, int]) -> dict[str, Any]:
    n, k, seed, condition, budget, policy_seed = item
    return {
        "k": k,
        "seed_sha256": hashlib.sha256(seed.encode()).hexdigest(),
        "condition": condition,
        "budget": budget,
        "policy_seed": policy_seed,
        **simulate(
            n=n,
            k=k,
            seed=seed,
            condition=condition,
            budget=budget,
            policy_seed=policy_seed,
        ),
    }


def summarize(
    rows: list[dict[str, Any]],
    references: dict[tuple[int, str], dict[str, float]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
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
    output: list[dict[str, Any]] = []
    effects: dict[tuple[int, int, str], list[float]] = {}
    for k in sorted({int(row["k"]) for row in rows}):
        for budget in BUDGETS:
            for treatment in ("partition_4", "multi_island_2", "multi_island_4"):
                raw_values: list[float] = []
                z_values: list[float] = []
                diversity_values: list[float] = []
                pair_keys = sorted(
                    {
                        (str(row["seed_sha256"]), int(row["policy_seed"]))
                        for row in rows
                        if int(row["k"]) == k and int(row["budget"]) == budget
                    }
                )
                for seed_hash, policy_seed in pair_keys:
                    left = indexed[(k, seed_hash, budget, policy_seed, treatment)]
                    right = indexed[(k, seed_hash, budget, policy_seed, "global_8")]
                    raw = float(left["best_score"]) - float(right["best_score"])
                    raw_values.append(raw)
                    z_values.append(raw / references[(k, seed_hash)]["random_sd"])
                    diversity_values.append(
                        float(left["final_diversity"])
                        - float(right["final_diversity"])
                    )
                low, high = common.bootstrap_interval(
                    z_values,
                    f"takeover:{k}:{budget}:{treatment}",
                )
                effects[(k, budget, treatment)] = z_values
                output.append(
                    {
                        "k": k,
                        "budget": budget,
                        "contrast": f"{treatment}_minus_global_8",
                        "paired_policy_runs": len(z_values),
                        "score_difference": statistics.fmean(raw_values),
                        "random_z_difference": statistics.fmean(z_values),
                        "random_z_ci_low": low,
                        "random_z_ci_high": high,
                        "win_rate": sum(value > 0 for value in raw_values)
                        / len(raw_values),
                        "diversity_difference": statistics.fmean(diversity_values),
                    }
                )
    passing = []
    for row in output:
        k = int(row["k"])
        budget = int(row["budget"])
        if k == 0 or row["contrast"] != "multi_island_4_minus_global_8":
            row["task_sensitivity_passes"] = False
            continue
        rugged = effects[(k, budget, "multi_island_4")]
        smooth = effects[(0, budget, "multi_island_4")]
        interaction = [
            rugged_value - smooth_value
            for rugged_value, smooth_value in zip(rugged, smooth, strict=True)
        ]
        interaction_low, interaction_high = common.bootstrap_interval(
            interaction,
            f"takeover-interaction:{k}:{budget}",
        )
        row["rugged_minus_smooth_random_z"] = statistics.fmean(interaction)
        row["rugged_minus_smooth_random_z_ci_low"] = interaction_low
        row["rugged_minus_smooth_random_z_ci_high"] = interaction_high
        passes = (
            float(row["random_z_difference"]) >= RUGGED_EFFECT_FLOOR_Z
            and float(row["random_z_ci_low"]) > 0
            and statistics.fmean(interaction) >= INTERACTION_FLOOR_Z
            and interaction_low > 0
        )
        row["task_sensitivity_passes"] = passes
        if passes:
            passing.append({"k": k, "budget": budget})
    selected = min(passing, key=lambda item: (item["budget"], item["k"])) if passing else None
    return output, {
        "rugged_effect_floor_random_z": RUGGED_EFFECT_FLOOR_Z,
        "rugged_minus_smooth_floor_random_z": INTERACTION_FLOOR_Z,
        "passing_k_budget_cells": passing,
        "calibration_supports_takeover_mechanism_study": bool(passing),
        "selection_rule": "earliest passing budget, then smallest K",
        "selected_rugged_k": selected["k"] if selected else None,
        "selected_threshold_anchor_budget": selected["budget"] if selected else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy-repetitions", type=int, default=8)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    landscape_data = json.loads(common.CALIBRATION_LANDSCAPES.read_text())
    n = int(landscape_data["n"])
    seeds = [str(seed) for seed in landscape_data["seeds"]]
    k_values = [int(k) for k in landscape_data["k_values"] if int(k) != 4]
    references = {
        (k, hashlib.sha256(seed.encode()).hexdigest()): common.random_reference(n, k, seed)
        for k in k_values
        for seed in seeds
    }
    items = [
        (n, k, seed, condition, budget, seed_index * 10_000 + repetition)
        for k in k_values
        for seed_index, seed in enumerate(seeds)
        for condition in CONDITIONS
        for budget in BUDGETS
        for repetition in range(args.policy_repetitions)
    ]
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(_work_item, items, chunksize=4))
    summary, decision = summarize(rows, references)
    payload = {
        "schema_version": 1,
        "method": "full visible-champion assimilation with mutation and cyclic migration",
        "interpretation": "conditional mechanism-positive check, not an LLM forecast",
        "calibration_seed_count": len(seeds),
        "policy_repetitions": args.policy_repetitions,
        "budgets": list(BUDGETS),
        "island_counts": [1, 2, 4],
        "decision": decision,
        "summary": summary,
    }
    rendered = json.dumps(payload, indent=2) + "\n"
    args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
