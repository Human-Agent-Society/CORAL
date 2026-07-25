#!/usr/bin/env python3
"""Screen a genuinely harder N=512 NK phase map before any LLM matrix.

This calibration extends the v3 social-learning simulator without changing
its move-not-copy migration semantics.  It crosses ruggedness, budget, and
mutation operator on landscape seeds that are disjoint from both v3 and the
future v4 participant bundle.  The selection rule distinguishes two claims:

* a boundary threshold, where multi-island beats global and the effect is
  larger on Rugged than Smooth; and
* a migration threshold, which additionally requires multi-island to beat a
  permanent four-way partition.

Four-bit mutation is a registered out-of-family stress test.  It is reported
but cannot be silently dropped or used to select the task after the fact.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import calibrate_threshold_v3_robustness as robustness
from experiments.multi_island_hard import calibrate_threshold_v3_social as social

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "threshold_v4_scale_calibration.json"
N = 512
K_VALUES = (0, 16, 32, 64, 128)
BUDGETS = (4096, 8192, 16384)
CONDITIONS = ("global_8", "partition_4", "multi_island_4")
MUTATION_POLICIES = social.MUTATION_POLICIES
LOCAL_MUTATION_FAMILY = ("one_bit", "registered_mixed", "broader")
CALIBRATION_LANDSCAPES = 8
POLICY_REPETITIONS = 4
BOOTSTRAP_REPETITIONS = 10_000
BOUNDARY_EFFECT_FLOOR_Z = 0.25
MIGRATION_EFFECT_FLOOR_Z = 0.10


@dataclass(frozen=True)
class WorkItem:
    k: int
    budget: int
    mutation: str
    seed: str
    policy_seed: int
    condition: str


def generated_seed(index: int) -> str:
    return hashlib.sha256(f"threshold-v4-scale-calibration:{index}".encode()).hexdigest()


def heldout_seed(index: int) -> str:
    """Reproduce the frozen participant bundle without sharing calibration seeds."""
    return hashlib.sha256(f"threshold-v4-heldout:{index}".encode()).hexdigest()


def policy_seed(index: int) -> int:
    return int.from_bytes(
        hashlib.sha256(f"threshold-v4-scale-policy:{index}".encode()).digest()[:8],
        "big",
    )


def run_item(item: WorkItem) -> tuple[WorkItem, float]:
    result = social.simulate(
        n=N,
        k=item.k,
        seed=item.seed,
        condition=item.condition,
        budget=item.budget,
        imitation=1.0,
        policy_seed=item.policy_seed,
        mutation_policy=item.mutation,
        initial_salt="coral-threshold-v4",
    )
    return item, float(result["best_score"])


def cluster_summary(
    values: dict[str, list[float]],
    *,
    label: str,
    bootstrap_repetitions: int,
) -> dict[str, Any]:
    seed = int.from_bytes(hashlib.sha256(label.encode()).digest()[:8], "big")
    return robustness.cluster_summary(
        values,
        bootstrap_repetitions=bootstrap_repetitions,
        bootstrap_seed=seed,
    )


def summarize(
    scores: dict[tuple[int, int, str, str, int, str], float],
    references: dict[tuple[int, str], float],
    *,
    k_values: tuple[int, ...],
    budgets: tuple[int, ...],
    mutations: tuple[str, ...],
    seeds: tuple[str, ...],
    policy_seeds: tuple[int, ...],
    bootstrap_repetitions: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for k in k_values:
        for budget in budgets:
            for mutation in mutations:
                for treatment, control in (
                    ("multi_island_4", "global_8"),
                    ("multi_island_4", "partition_4"),
                ):
                    by_landscape: dict[str, list[float]] = defaultdict(list)
                    for seed in seeds:
                        scale = references[(k, seed)]
                        for stochastic_seed in policy_seeds:
                            key = (k, budget, mutation, seed, stochastic_seed)
                            by_landscape[seed].append(
                                (scores[(*key, treatment)] - scores[(*key, control)]) / scale
                            )
                    label = f"v4:{k}:{budget}:{mutation}:{treatment}:{control}"
                    rows.append(
                        {
                            "k": k,
                            "budget": budget,
                            "mutation": mutation,
                            "contrast": f"{treatment}_minus_{control}",
                            **cluster_summary(
                                by_landscape,
                                label=label,
                                bootstrap_repetitions=bootstrap_repetitions,
                            ),
                        }
                    )

                if k == 0 or 0 not in k_values:
                    continue
                interaction_by_landscape: dict[str, list[float]] = defaultdict(list)
                for seed in seeds:
                    rugged_scale = references[(k, seed)]
                    smooth_scale = references[(0, seed)]
                    for stochastic_seed in policy_seeds:
                        rugged_key = (k, budget, mutation, seed, stochastic_seed)
                        smooth_key = (0, budget, mutation, seed, stochastic_seed)
                        rugged_effect = (
                            scores[(*rugged_key, "multi_island_4")]
                            - scores[(*rugged_key, "global_8")]
                        ) / rugged_scale
                        smooth_effect = (
                            scores[(*smooth_key, "multi_island_4")]
                            - scores[(*smooth_key, "global_8")]
                        ) / smooth_scale
                        interaction_by_landscape[seed].append(rugged_effect - smooth_effect)
                rows.append(
                    {
                        "k": k,
                        "budget": budget,
                        "mutation": mutation,
                        "contrast": "rugged_minus_smooth_multi_island_4_minus_global_8",
                        **cluster_summary(
                            interaction_by_landscape,
                            label=f"v4:{k}:{budget}:{mutation}:interaction",
                            bootstrap_repetitions=bootstrap_repetitions,
                        ),
                    }
                )
    return rows


def _passes(row: dict[str, Any] | None, floor: float) -> bool:
    return bool(
        row is not None
        and float(row["mean_random_z_difference"]) >= floor
        and float(row["cluster_bootstrap_ci_low"]) > 0
    )


def select_threshold(
    rows: list[dict[str, Any]],
    *,
    k_values: tuple[int, ...],
    budgets: tuple[int, ...],
) -> dict[str, Any]:
    indexed = {
        (int(row["k"]), int(row["budget"]), str(row["mutation"]), str(row["contrast"])): row
        for row in rows
    }
    decisions: list[dict[str, Any]] = []
    boundary_threshold: dict[str, int] | None = None
    migration_threshold: dict[str, int] | None = None
    four_bit_threshold: dict[str, int] | None = None
    for budget in sorted(budgets):
        for k in sorted(value for value in k_values if value > 0):
            boundary_by_operator: dict[str, bool] = {}
            migration_by_operator: dict[str, bool] = {}
            for mutation in LOCAL_MUTATION_FAMILY:
                multi_global = indexed.get(
                    (k, budget, mutation, "multi_island_4_minus_global_8")
                )
                interaction = indexed.get(
                    (
                        k,
                        budget,
                        mutation,
                        "rugged_minus_smooth_multi_island_4_minus_global_8",
                    )
                )
                multi_partition = indexed.get(
                    (k, budget, mutation, "multi_island_4_minus_partition_4")
                )
                boundary_by_operator[mutation] = _passes(
                    multi_global, BOUNDARY_EFFECT_FLOOR_Z
                ) and _passes(interaction, BOUNDARY_EFFECT_FLOOR_Z)
                migration_by_operator[mutation] = boundary_by_operator[mutation] and _passes(
                    multi_partition, MIGRATION_EFFECT_FLOOR_Z
                )
            four_global = indexed.get(
                (k, budget, "four_bit", "multi_island_4_minus_global_8")
            )
            four_interaction = indexed.get(
                (
                    k,
                    budget,
                    "four_bit",
                    "rugged_minus_smooth_multi_island_4_minus_global_8",
                )
            )
            four_partition = indexed.get(
                (k, budget, "four_bit", "multi_island_4_minus_partition_4")
            )
            boundary_passes = all(boundary_by_operator.values())
            migration_passes = all(migration_by_operator.values())
            four_bit_passes = (
                _passes(four_global, BOUNDARY_EFFECT_FLOOR_Z)
                and _passes(four_interaction, BOUNDARY_EFFECT_FLOOR_Z)
                and _passes(four_partition, MIGRATION_EFFECT_FLOOR_Z)
            )
            decisions.append(
                {
                    "k": k,
                    "budget": budget,
                    "boundary_by_local_operator": boundary_by_operator,
                    "migration_by_local_operator": migration_by_operator,
                    "boundary_threshold_passes": boundary_passes,
                    "migration_threshold_passes": migration_passes,
                    "four_bit_generalization_passes": four_bit_passes,
                }
            )
            if boundary_passes and boundary_threshold is None:
                boundary_threshold = {"k": k, "budget": budget}
            if migration_passes and migration_threshold is None:
                migration_threshold = {"k": k, "budget": budget}
            if four_bit_passes and four_bit_threshold is None:
                four_bit_threshold = {"k": k, "budget": budget}
    return {
        "selection_order": "earliest budget, then smallest positive K",
        "boundary_effect_floor_random_z": BOUNDARY_EFFECT_FLOOR_Z,
        "migration_effect_floor_random_z": MIGRATION_EFFECT_FLOOR_Z,
        "required_local_mutation_family": list(LOCAL_MUTATION_FAMILY),
        "earliest_boundary_threshold": boundary_threshold,
        "earliest_migration_threshold": migration_threshold,
        "earliest_four_bit_generalization_threshold": four_bit_threshold,
        "cells": decisions,
    }


def run_calibration(
    *,
    k_values: tuple[int, ...],
    budgets: tuple[int, ...],
    landscape_repetitions: int,
    policy_repetitions: int,
    bootstrap_repetitions: int,
    max_workers: int,
) -> dict[str, Any]:
    if 0 not in k_values:
        raise ValueError("K=0 is required for the registered Smooth interaction control")
    seeds = tuple(generated_seed(index) for index in range(landscape_repetitions))
    policy_seeds = tuple(policy_seed(index) for index in range(policy_repetitions))
    references = {
        (k, seed): social.random_reference(N, k, seed, samples=256)["random_sd"]
        for k in k_values
        for seed in seeds
    }
    items = [
        WorkItem(k, budget, mutation, seed, stochastic_seed, condition)
        for k in k_values
        for budget in budgets
        for mutation in MUTATION_POLICIES
        for seed in seeds
        for stochastic_seed in policy_seeds
        for condition in CONDITIONS
    ]
    scores: dict[tuple[int, int, str, str, int, str], float] = {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as pool:
        for item, score in pool.map(run_item, items, chunksize=1):
            scores[
                (
                    item.k,
                    item.budget,
                    item.mutation,
                    item.seed,
                    item.policy_seed,
                    item.condition,
                )
            ] = score
    summaries = summarize(
        scores,
        references,
        k_values=k_values,
        budgets=budgets,
        mutations=MUTATION_POLICIES,
        seeds=seeds,
        policy_seeds=policy_seeds,
        bootstrap_repetitions=bootstrap_repetitions,
    )
    fully_registered = (
        k_values == K_VALUES
        and budgets == BUDGETS
        and landscape_repetitions == CALIBRATION_LANDSCAPES
        and policy_repetitions == POLICY_REPETITIONS
        and bootstrap_repetitions == BOOTSTRAP_REPETITIONS
    )
    return {
        "schema_version": 1,
        "purpose": "N=512 Smooth/Rugged topology threshold calibration",
        "n": N,
        "k_values": list(k_values),
        "budgets": list(budgets),
        "imitation": 1.0,
        "conditions": list(CONDITIONS),
        "mutation_policies": list(MUTATION_POLICIES),
        "landscape_repetitions": landscape_repetitions,
        "policy_repetitions_per_landscape": policy_repetitions,
        "inference_unit": "landscape seed; policy repetitions averaged within seed",
        "calibration_seed_sha256": [hashlib.sha256(seed.encode()).hexdigest() for seed in seeds],
        "fully_registered_run": fully_registered,
        "summaries": summaries,
        "decision": select_threshold(summaries, k_values=k_values, budgets=budgets),
        "interpretation": (
            "Boundary and migration thresholds are separate. A boundary-only pass cannot be "
            "reported as evidence that selective migration beats permanent partition."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ks", type=int, nargs="+", default=list(K_VALUES))
    parser.add_argument("--budgets", type=int, nargs="+", default=list(BUDGETS))
    parser.add_argument("--landscapes", type=int, default=CALIBRATION_LANDSCAPES)
    parser.add_argument("--policy-repetitions", type=int, default=POLICY_REPETITIONS)
    parser.add_argument("--bootstrap-repetitions", type=int, default=BOOTSTRAP_REPETITIONS)
    parser.add_argument("--max-workers", type=int, default=8)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    k_values = tuple(sorted(set(args.ks)))
    budgets = tuple(sorted(set(args.budgets)))
    if (
        args.landscapes < 2
        or args.policy_repetitions < 1
        or args.bootstrap_repetitions < 100
        or args.max_workers < 1
    ):
        raise SystemExit("need >=2 landscapes, >=1 policy run, >=100 bootstraps, >=1 worker")
    result = run_calibration(
        k_values=k_values,
        budgets=budgets,
        landscape_repetitions=args.landscapes,
        policy_repetitions=args.policy_repetitions,
        bootstrap_repetitions=args.bootstrap_repetitions,
        max_workers=args.max_workers,
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["decision"], indent=2))
    if args.output == DEFAULT_OUTPUT and not result["fully_registered_run"]:
        raise SystemExit("refusing to treat a reduced calibration as the registered v4 result")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
