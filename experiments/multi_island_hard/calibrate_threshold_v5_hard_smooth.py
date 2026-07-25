#!/usr/bin/env python3
"""Calibrate a non-saturating Smooth control against the frozen v4 Rugged grid.

The additive K=0 control is useful but reaches its exact optimum by B=16,384.
This follow-up replaces it with a hidden-target, hidden-order Permuted
LeadingOnes landscape. Every non-optimal point has exactly one improving
one-bit neighbor and the optimum is unique, but the private permutation hides
which coordinate comes next. It therefore separates task difficulty from
rugged multi-basin geometry without giving an adaptive agent an O(N) shortcut.

The Rugged side is not reselected from participant data: this script joins a
new, fully paired Permuted LeadingOnes simulation to the frozen N=512 v4 NK
calibration on the same calibration seeds, policy seeds, budgets, topologies,
and mutation operators.  Random-z values are not subtracted across the two
families because their null variances are incommensurate.  The registered hard
anchor must instead pass the original within-NK ruggedness interaction and
migration gates, while the hard Smooth task independently shows no saturation
and the opposite topology direction.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import calibrate_threshold_v3_robustness as robustness
from experiments.multi_island_hard import calibrate_threshold_v3_social as social
from experiments.multi_island_hard import calibrate_threshold_v4_scale as v4

ROOT = Path(__file__).resolve().parent
V4_CALIBRATION = ROOT / "threshold_v4_scale_calibration.json"
DEFAULT_OUTPUT = ROOT / "threshold_v5_hard_smooth_calibration.json"
N = v4.N
BUDGETS = v4.BUDGETS
CONDITIONS = v4.CONDITIONS
MUTATION_POLICIES = v4.MUTATION_POLICIES
LOCAL_MUTATION_FAMILY = v4.LOCAL_MUTATION_FAMILY
LANDSCAPE_REPETITIONS = v4.CALIBRATION_LANDSCAPES
POLICY_REPETITIONS = v4.POLICY_REPETITIONS
BOOTSTRAP_REPETITIONS = v4.BOOTSTRAP_REPETITIONS


@dataclass(frozen=True)
class PathIndividual:
    candidate: str
    score: float
    lineage: str


@dataclass(frozen=True)
class WorkItem:
    budget: int
    mutation: str
    seed: str
    policy_seed: int
    condition: str


def hidden_target(seed: str, n: int = N) -> str:
    digest = hashlib.sha256(f"permuted-leading-ones:{seed}".encode()).digest()
    bits = "".join(f"{byte:08b}" for byte in digest)
    while len(bits) < n:
        digest = hashlib.sha256(digest).digest()
        bits += "".join(f"{byte:08b}" for byte in digest)
    return bits[:n]


def hidden_coordinate_order(seed: str, n: int = N) -> tuple[int, ...]:
    return tuple(
        sorted(
            range(n),
            key=lambda index: hashlib.sha256(
                f"permuted-leading-order:{seed}:{index}".encode()
            ).digest(),
        )
    )


def leading_ones(candidate: str, target: str, order: tuple[int, ...]) -> int:
    for prefix, index in enumerate(order):
        if candidate[index] != target[index]:
            return prefix
    return len(candidate)


def mutate(
    parent: PathIndividual,
    *,
    target: str,
    order: tuple[int, ...],
    rng: random.Random,
    mutation_policy: str,
) -> PathIndividual:
    flips = social.mutation_indices(rng, len(parent.candidate), mutation_policy)
    bits = list(parent.candidate)
    for index in flips:
        bits[index] = "0" if bits[index] == "1" else "1"
    candidate = "".join(bits)
    return PathIndividual(
        candidate=candidate,
        score=leading_ones(candidate, target, order) / len(candidate),
        lineage=parent.lineage,
    )


def simulate(item: WorkItem) -> tuple[WorkItem, dict[str, Any]]:
    island_count = social.ISLAND_COUNTS[item.condition]
    rng = random.Random(item.policy_seed)
    target = hidden_target(item.seed)
    order = hidden_coordinate_order(item.seed)
    states = []
    for slot, agent_id in enumerate(social.BASE_AGENT_IDS):
        candidate = social.initial_candidate(agent_id, N, "coral-threshold-v4")
        states.append(
            social.AgentState(
                agent_id=agent_id,
                island=social.initial_island(slot, island_count),
                incumbent=PathIndividual(
                    candidate=candidate,
                    score=leading_ones(candidate, target, order) / N,
                    lineage=agent_id,
                ),
            )
        )
    best_score = max(state.incumbent.score for state in states)
    evaluations = len(states)
    migration_boundaries = {
        item.budget // 4,
        item.budget // 2,
        3 * item.budget // 4,
    }
    while evaluations < item.budget:
        state = states[evaluations % len(states)]
        peers = social.visible(states, state.island)
        champion = max(
            peers,
            key=lambda peer: (peer.incumbent.score, peer.agent_id),
        )
        # Full visible-champion diffusion is the registered mechanism arm.
        # Consume the same imitation draw as the frozen v4 NK simulator so
        # paired policy seeds induce the same mutation schedule.
        rng.random()
        parent = champion.incumbent
        child = mutate(
            parent,
            target=target,
            order=order,
            rng=rng,
            mutation_policy=item.mutation,
        )
        evaluations += 1
        best_score = max(best_score, child.score)
        if child.score > state.incumbent.score:
            state.incumbent = child
        if evaluations in migration_boundaries and item.condition == "multi_island_4":
            social.rotate_champions(states, island_count, "elite")
    return item, {
        "best_score": best_score,
        "best_prefix": round(best_score * N),
        "exact": best_score == 1.0,
    }


def leading_ones_random_sd(n: int = N) -> float:
    probabilities = [2 ** (-(matches + 1)) for matches in range(n)]
    probabilities.append(2**-n)
    values = [matches / n for matches in range(n + 1)]
    mean = sum(value * probability for value, probability in zip(values, probabilities))
    variance = sum(
        probability * (value - mean) ** 2
        for value, probability in zip(values, probabilities)
    )
    return math.sqrt(variance)


def cluster_summary(
    by_landscape: dict[str, list[float]],
    *,
    label: str,
    bootstrap_repetitions: int,
) -> dict[str, Any]:
    seed = int.from_bytes(hashlib.sha256(label.encode()).digest()[:8], "big")
    return robustness.cluster_summary(
        by_landscape,
        bootstrap_repetitions=bootstrap_repetitions,
        bootstrap_seed=seed,
    )


def summarize_smooth(
    scores: dict[tuple[int, str, str, int, str], dict[str, Any]],
    *,
    budgets: tuple[int, ...],
    mutations: tuple[str, ...],
    seeds: tuple[str, ...],
    policy_seeds: tuple[int, ...],
    bootstrap_repetitions: int,
) -> list[dict[str, Any]]:
    scale = leading_ones_random_sd()
    rows: list[dict[str, Any]] = []
    for budget in budgets:
        for mutation in mutations:
            for treatment, control in (
                ("multi_island_4", "global_8"),
                ("multi_island_4", "partition_4"),
            ):
                by_landscape: dict[str, list[float]] = {seed: [] for seed in seeds}
                for seed in seeds:
                    for stochastic_seed in policy_seeds:
                        prefix = (budget, mutation, seed, stochastic_seed)
                        by_landscape[seed].append(
                            (
                                float(scores[(*prefix, treatment)]["best_score"])
                                - float(scores[(*prefix, control)]["best_score"])
                            )
                            / scale
                        )
                rows.append(
                    {
                        "family": "permuted_leading_ones",
                        "budget": budget,
                        "mutation": mutation,
                        "contrast": f"{treatment}_minus_{control}",
                        **cluster_summary(
                            by_landscape,
                            label=f"v5-leading:{budget}:{mutation}:{treatment}:{control}",
                            bootstrap_repetitions=bootstrap_repetitions,
                        ),
                    }
                )
            global_results = [
                scores[(budget, mutation, seed, stochastic_seed, "global_8")]
                for seed in seeds
                for stochastic_seed in policy_seeds
            ]
            rows.append(
                {
                    "family": "permuted_leading_ones",
                    "budget": budget,
                    "mutation": mutation,
                    "contrast": "global_hardness_diagnostic",
                    "paired_runs": len(global_results),
                    "mean_best_prefix": statistics.fmean(
                        int(result["best_prefix"]) for result in global_results
                    ),
                    "max_best_prefix": max(
                        int(result["best_prefix"]) for result in global_results
                    ),
                    "exact_solutions": sum(bool(result["exact"]) for result in global_results),
                }
            )
    return rows


def rugged_row(
    rows: list[dict[str, Any]],
    *,
    k: int,
    budget: int,
    mutation: str,
    contrast: str,
) -> dict[str, Any]:
    return next(
        row
        for row in rows
        if int(row["k"]) == k
        and int(row["budget"]) == budget
        and row["mutation"] == mutation
        and row["contrast"] == contrast
    )


def passes(row: dict[str, Any], floor: float) -> bool:
    return bool(
        float(row["mean_random_z_difference"]) >= floor
        and float(row["cluster_bootstrap_ci_low"]) > 0
    )


def select_anchor(
    rugged: list[dict[str, Any]],
    smooth: list[dict[str, Any]],
    *,
    k_values: tuple[int, ...],
    budgets: tuple[int, ...],
) -> dict[str, Any]:
    cells = []
    selected = None
    for budget in sorted(budgets):
        for k in sorted(k_values):
            by_operator = {}
            for mutation in LOCAL_MUTATION_FAMILY:
                multi_global = rugged_row(
                    rugged,
                    k=k,
                    budget=budget,
                    mutation=mutation,
                    contrast="multi_island_4_minus_global_8",
                )
                multi_partition = rugged_row(
                    rugged,
                    k=k,
                    budget=budget,
                    mutation=mutation,
                    contrast="multi_island_4_minus_partition_4",
                )
                within_nk_interaction = rugged_row(
                    rugged,
                    k=k,
                    budget=budget,
                    mutation=mutation,
                    contrast="rugged_minus_smooth_multi_island_4_minus_global_8",
                )
                hard_smooth_effect = next(
                    row
                    for row in smooth
                    if row["budget"] == budget
                    and row["mutation"] == mutation
                    and row["contrast"] == "multi_island_4_minus_global_8"
                )
                hardness = next(
                    row
                    for row in smooth
                    if row["budget"] == budget
                    and row["mutation"] == mutation
                    and row["contrast"] == "global_hardness_diagnostic"
                )
                by_operator[mutation] = {
                    "rugged_beats_global": passes(
                        multi_global,
                        v4.BOUNDARY_EFFECT_FLOOR_Z,
                    ),
                    "rugged_beats_partition": passes(
                        multi_partition,
                        v4.MIGRATION_EFFECT_FLOOR_Z,
                    ),
                    "within_nk_ruggedness_interaction": passes(
                        within_nk_interaction,
                        v4.BOUNDARY_EFFECT_FLOOR_Z,
                    ),
                    "hard_smooth_global_beats_multi": (
                        float(hard_smooth_effect["cluster_bootstrap_ci_high"]) < 0
                    ),
                    "hard_smooth_not_saturated": hardness["exact_solutions"] == 0,
                }
            cell_passes = all(all(gates.values()) for gates in by_operator.values())
            cells.append(
                {
                    "k": k,
                    "budget": budget,
                    "by_local_operator": by_operator,
                    "hard_anchor_passes": cell_passes,
                }
            )
            if cell_passes and selected is None:
                selected = {"k": k, "budget": budget}
    return {
        "selection_order": "earliest budget, then smallest K",
        "required_local_mutation_family": list(LOCAL_MUTATION_FAMILY),
        "boundary_floor_random_z": v4.BOUNDARY_EFFECT_FLOOR_Z,
        "migration_floor_random_z": v4.MIGRATION_EFFECT_FLOOR_Z,
        "selected_hard_anchor": selected,
        "cells": cells,
    }


def run_calibration(
    *,
    budgets: tuple[int, ...],
    landscape_repetitions: int,
    policy_repetitions: int,
    bootstrap_repetitions: int,
    max_workers: int,
) -> dict[str, Any]:
    v4_data = json.loads(V4_CALIBRATION.read_text())
    if not v4_data.get("fully_registered_run"):
        raise ValueError("v5 requires the complete frozen v4 Rugged calibration")
    rugged = list(v4_data["summaries"])
    k_values = tuple(int(value) for value in v4_data["k_values"] if int(value) > 0)
    seeds = tuple(v4.generated_seed(index) for index in range(landscape_repetitions))
    policy_seeds = tuple(v4.policy_seed(index) for index in range(policy_repetitions))
    expected_hashes = [hashlib.sha256(seed.encode()).hexdigest() for seed in seeds]
    if expected_hashes != v4_data["calibration_seed_sha256"][:landscape_repetitions]:
        raise ValueError("v4 calibration seed order cannot be reproduced")
    items = [
        WorkItem(budget, mutation, seed, stochastic_seed, condition)
        for budget in budgets
        for mutation in MUTATION_POLICIES
        for seed in seeds
        for stochastic_seed in policy_seeds
        for condition in CONDITIONS
    ]
    scores: dict[tuple[int, str, str, int, str], dict[str, Any]] = {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as pool:
        for item, result in pool.map(simulate, items, chunksize=1):
            scores[
                (
                    item.budget,
                    item.mutation,
                    item.seed,
                    item.policy_seed,
                    item.condition,
                )
            ] = result
    smooth = summarize_smooth(
        scores,
        budgets=budgets,
        mutations=MUTATION_POLICIES,
        seeds=seeds,
        policy_seeds=policy_seeds,
        bootstrap_repetitions=bootstrap_repetitions,
    )
    fully_registered = (
        budgets == BUDGETS
        and landscape_repetitions == LANDSCAPE_REPETITIONS
        and policy_repetitions == POLICY_REPETITIONS
        and bootstrap_repetitions == BOOTSTRAP_REPETITIONS
    )
    return {
        "schema_version": 1,
        "purpose": "non-saturating hidden-order Smooth versus high-epistasis Rugged threshold",
        "n": N,
        "smooth_family": "hidden-target hidden-order permuted_leading_ones",
        "rugged_family": "adjacent NK from frozen v4 calibration",
        "k_values": list(k_values),
        "budgets": list(budgets),
        "conditions": list(CONDITIONS),
        "mutation_policies": list(MUTATION_POLICIES),
        "landscape_repetitions": landscape_repetitions,
        "policy_repetitions_per_landscape": policy_repetitions,
        "calibration_seed_sha256": expected_hashes,
        "fully_registered_run": fully_registered,
        "smooth_summaries": smooth,
        "rugged_summaries_source": str(V4_CALIBRATION.relative_to(ROOT)),
        "cross_family_standardized_interaction": None,
        "cross_family_interaction_reason": (
            "Permuted LeadingOnes and NK random-baseline variances are not commensurate; "
            "directional gates are reported separately instead of subtracting z-scores."
        ),
        "decision": select_anchor(
            rugged,
            smooth,
            k_values=k_values,
            budgets=budgets,
        ),
        "interpretation": (
            "This is scripted topology-mechanism calibration. It cannot establish "
            "a natural-agent or institutions claim."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--budgets", type=int, nargs="+", default=list(BUDGETS))
    parser.add_argument("--landscapes", type=int, default=LANDSCAPE_REPETITIONS)
    parser.add_argument("--policy-repetitions", type=int, default=POLICY_REPETITIONS)
    parser.add_argument("--bootstrap-repetitions", type=int, default=BOOTSTRAP_REPETITIONS)
    parser.add_argument("--max-workers", type=int, default=8)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    budgets = tuple(sorted(set(args.budgets)))
    if (
        any(budget not in BUDGETS for budget in budgets)
        or args.landscapes < 2
        or args.policy_repetitions < 1
        or args.bootstrap_repetitions < 100
        or args.max_workers < 1
    ):
        raise SystemExit("invalid v5 calibration reduction")
    result = run_calibration(
        budgets=budgets,
        landscape_repetitions=args.landscapes,
        policy_repetitions=args.policy_repetitions,
        bootstrap_repetitions=args.bootstrap_repetitions,
        max_workers=args.max_workers,
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["decision"], indent=2))
    if args.output == DEFAULT_OUTPUT and not result["fully_registered_run"]:
        raise SystemExit("refusing reduced output at the registered v5 path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
