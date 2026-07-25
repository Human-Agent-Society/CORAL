#!/usr/bin/env python3
"""Falsify the selected NK threshold under operator and migration changes.

The phase map selected K=32/B=4096 with one registered local-mutation mix and
elite move-not-copy migration.  This audit uses fresh landscapes to ask two
questions before spending more LLM budget:

1. Does the multi-island contrast survive plausible mutation operators?
2. Does elite selection add anything beyond moving some resident?

Landscape seeds, rather than stochastic policy repetitions, are the unit of
generalization.  Intervals therefore use a cluster bootstrap over per-
landscape paired means.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import calibrate_threshold_v3_social as social

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "threshold_v3_robustness.json"
N = 256
K = 32
BUDGET = 4096
LANDSCAPE_REPETITIONS = 8
POLICY_REPETITIONS = 8
BOOTSTRAP_REPETITIONS = 10_000


def generated_seed(namespace: str, index: int) -> str:
    return hashlib.sha256(f"threshold-v3-robustness-{namespace}:{index}".encode()).hexdigest()


def policy_seed(index: int) -> int:
    return int.from_bytes(
        hashlib.sha256(f"threshold-v3-robustness-policy:{index}".encode()).digest()[:8],
        "big",
    )


def cluster_summary(
    by_landscape: dict[str, list[float]],
    *,
    bootstrap_repetitions: int = BOOTSTRAP_REPETITIONS,
    bootstrap_seed: int = 20260725,
) -> dict[str, Any]:
    cluster_means = [statistics.fmean(values) for values in by_landscape.values()]
    rng = random.Random(bootstrap_seed)
    bootstraps = sorted(
        statistics.fmean(rng.choice(cluster_means) for _ in cluster_means)
        for _ in range(bootstrap_repetitions)
    )
    low = bootstraps[int(0.025 * (bootstrap_repetitions - 1))]
    high = bootstraps[int(0.975 * (bootstrap_repetitions - 1))]
    flattened = [value for values in by_landscape.values() for value in values]
    return {
        "landscape_clusters": len(cluster_means),
        "policy_runs_per_landscape": len(flattened) // len(cluster_means),
        "paired_runs": len(flattened),
        "mean_random_z_difference": statistics.fmean(cluster_means),
        "cluster_bootstrap_ci_low": low,
        "cluster_bootstrap_ci_high": high,
        "paired_win_rate": sum(value > 0 for value in flattened) / len(flattened),
        "per_landscape_mean_random_z": cluster_means,
    }


def run_audit(
    *,
    landscape_repetitions: int = LANDSCAPE_REPETITIONS,
    policy_repetitions: int = POLICY_REPETITIONS,
    bootstrap_repetitions: int = BOOTSTRAP_REPETITIONS,
) -> dict[str, Any]:
    seeds = [generated_seed("landscape", index) for index in range(landscape_repetitions)]
    policies = [policy_seed(index) for index in range(policy_repetitions)]
    references = {
        seed: social.random_reference(N, K, seed, samples=256)["random_sd"] for seed in seeds
    }

    mutation_differences = {
        mutation: {seed: [] for seed in seeds} for mutation in social.MUTATION_POLICIES
    }
    migration_global = {seed: [] for seed in seeds}
    migration_partition = {seed: [] for seed in seeds}
    migration_multi = {
        selection: {seed: [] for seed in seeds}
        for selection in social.MIGRATION_SELECTIONS
    }

    for seed in seeds:
        scale = references[seed]
        for stochastic_seed in policies:
            one_bit_global = social.simulate(
                n=N,
                k=K,
                seed=seed,
                condition="global_8",
                budget=BUDGET,
                imitation=1.0,
                policy_seed=stochastic_seed,
                mutation_policy="one_bit",
            )["best_score"]
            one_bit_partition = social.simulate(
                n=N,
                k=K,
                seed=seed,
                condition="partition_4",
                budget=BUDGET,
                imitation=1.0,
                policy_seed=stochastic_seed,
                mutation_policy="one_bit",
            )["best_score"]
            migration_global[seed].append(one_bit_global)
            migration_partition[seed].append(one_bit_partition)

            for selection in social.MIGRATION_SELECTIONS:
                score = social.simulate(
                    n=N,
                    k=K,
                    seed=seed,
                    condition="multi_island_4",
                    budget=BUDGET,
                    imitation=1.0,
                    policy_seed=stochastic_seed,
                    mutation_policy="one_bit",
                    migration_selection=selection,
                )["best_score"]
                migration_multi[selection][seed].append(score)

            mutation_differences["one_bit"][seed].append(
                (migration_multi["elite"][seed][-1] - one_bit_global) / scale
            )
            for mutation in social.MUTATION_POLICIES[1:]:
                global_score = social.simulate(
                    n=N,
                    k=K,
                    seed=seed,
                    condition="global_8",
                    budget=BUDGET,
                    imitation=1.0,
                    policy_seed=stochastic_seed,
                    mutation_policy=mutation,
                )["best_score"]
                multi_score = social.simulate(
                    n=N,
                    k=K,
                    seed=seed,
                    condition="multi_island_4",
                    budget=BUDGET,
                    imitation=1.0,
                    policy_seed=stochastic_seed,
                    mutation_policy=mutation,
                )["best_score"]
                mutation_differences[mutation][seed].append((multi_score - global_score) / scale)

    mutation_results = {
        mutation: cluster_summary(
            values,
            bootstrap_repetitions=bootstrap_repetitions,
            bootstrap_seed=20260725 + index,
        )
        for index, (mutation, values) in enumerate(mutation_differences.items())
    }
    migration_results: dict[str, Any] = {}
    for index, selection in enumerate(social.MIGRATION_SELECTIONS):
        minus_global = {
            seed: [
                (multi - global_score) / references[seed]
                for multi, global_score in zip(
                    migration_multi[selection][seed], migration_global[seed], strict=True
                )
            ]
            for seed in seeds
        }
        minus_partition = {
            seed: [
                (multi - partition_score) / references[seed]
                for multi, partition_score in zip(
                    migration_multi[selection][seed], migration_partition[seed], strict=True
                )
            ]
            for seed in seeds
        }
        migration_results[selection] = {
            "multi_island_4_minus_global_8": cluster_summary(
                minus_global,
                bootstrap_repetitions=bootstrap_repetitions,
                bootstrap_seed=20260825 + index,
            ),
            "multi_island_4_minus_partition_4": cluster_summary(
                minus_partition,
                bootstrap_repetitions=bootstrap_repetitions,
                bootstrap_seed=20260925 + index,
            ),
        }

    elite = migration_results["elite"]["multi_island_4_minus_partition_4"]
    non_elite = [
        migration_results[name]["multi_island_4_minus_partition_4"]
        for name in ("fixed_identity", "worst")
    ]
    return {
        "schema_version": 1,
        "purpose": "out-of-selection falsification of the K=32/B=4096 NK anchor",
        "n": N,
        "k": K,
        "budget": BUDGET,
        "imitation": 1.0,
        "landscape_seed_sha256": [hashlib.sha256(seed.encode()).hexdigest() for seed in seeds],
        "landscape_repetitions": landscape_repetitions,
        "policy_repetitions_per_landscape": policy_repetitions,
        "inference_unit": "landscape seed; stochastic policy runs are averaged within seed",
        "mutation_robustness": mutation_results,
        "migration_selection_robustness": migration_results,
        "decision": {
            "is_universal_over_tested_mutations": all(
                row["cluster_bootstrap_ci_low"] > 0 for row in mutation_results.values()
            ),
            "elite_selection_identified": elite["mean_random_z_difference"]
            > max(row["mean_random_z_difference"] for row in non_elite),
            "required_interpretation": (
                "An effect is conditional on the mutation operator. A positive elite-migration "
                "contrast alone identifies periodic mixing, not the value of selecting elites, "
                "unless it exceeds matched non-elite migration controls."
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--landscapes", type=int, default=LANDSCAPE_REPETITIONS)
    parser.add_argument("--policy-repetitions", type=int, default=POLICY_REPETITIONS)
    parser.add_argument("--bootstrap-repetitions", type=int, default=BOOTSTRAP_REPETITIONS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.landscapes < 2 or args.policy_repetitions < 1 or args.bootstrap_repetitions < 100:
        raise SystemExit("need >=2 landscapes, >=1 policy repetition, and >=100 bootstraps")
    result = run_audit(
        landscape_repetitions=args.landscapes,
        policy_repetitions=args.policy_repetitions,
        bootstrap_repetitions=args.bootstrap_repetitions,
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["decision"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
