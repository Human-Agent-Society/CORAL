#!/usr/bin/env python3
"""Map where islands help as visible-champion imitation increases.

This calibration models the behavior that the city-state claim actually
depends on. Agents either mutate their own incumbent or, with probability
``imitation``, mutate the best incumbent visible in their current island.
Migration *moves* one champion per island in a cyclic exchange; it never
clones a candidate. Thus imitation=0 is an exact topology-null control, while
higher values expose the exploration/exploitation phase transition without
assuming that real LLM agents always copy a champion.
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

ROOT = Path(__file__).resolve().parent
LANDSCAPES = ROOT / "threshold_v3_calibration_landscapes.json"
DEFAULT_OUTPUT = ROOT / "threshold_v3_social_calibration.json"
BUDGETS = (256, 512, 1024, 2048, 4096, 8192)
IMITATION_LEVELS = (0.0, 0.25, 0.5, 0.75, 1.0)
CONDITIONS = ("global_8", "partition_4", "multi_island_2", "multi_island_4")
ISLAND_COUNTS = {
    "global_8": 1,
    "partition_4": 4,
    "multi_island_2": 2,
    "multi_island_4": 4,
}
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
RUGGED_EFFECT_FLOOR_Z = 0.25
INTERACTION_FLOOR_Z = 0.25
# The landscape anchor is selected in an explicit full-diffusion positive
# control. Natural LLM runs are analyzed against their observed imitation
# rate and are never assumed to live at this endpoint.
SELECTION_IMITATION = 1.0


@dataclass(frozen=True)
class Individual:
    candidate: str
    components: tuple[float, ...]
    total: float
    lineage: str

    @property
    def score(self) -> float:
        return self.total / len(self.components)


@dataclass
class AgentState:
    agent_id: str
    island: int
    incumbent: Individual


def initial_candidate(agent_id: str, n: int) -> str:
    digest = hashlib.sha256(f"coral-threshold-v3:{agent_id}".encode()).digest()
    bits = "".join(f"{byte:08b}" for byte in digest)
    while len(bits) < n:
        digest = hashlib.sha256(digest).digest()
        bits += "".join(f"{byte:08b}" for byte in digest)
    return bits[:n]


def contribution(candidate: str, index: int, *, k: int, seed: str) -> float:
    n = len(candidate)
    pattern = "".join(candidate[(index + offset) % n] for offset in range(k + 1))
    digest = hashlib.sha256(f"{seed}:{index}:{pattern}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def make_individual(candidate: str, *, k: int, seed: str, lineage: str) -> Individual:
    components = tuple(
        contribution(candidate, index, k=k, seed=seed) for index in range(len(candidate))
    )
    return Individual(candidate, components, sum(components), lineage)


def mutation_indices(rng: random.Random, n: int) -> tuple[int, ...]:
    draw = rng.random()
    count = 1 if draw < 0.90 else 2 if draw < 0.98 else 4
    return tuple(sorted(rng.sample(range(n), count)))


def mutate(
    parent: Individual,
    *,
    k: int,
    seed: str,
    rng: random.Random,
) -> Individual:
    flips = mutation_indices(rng, len(parent.candidate))
    bits = list(parent.candidate)
    for index in flips:
        bits[index] = "1" if bits[index] == "0" else "0"
    candidate = "".join(bits)
    affected = {(index - offset) % len(bits) for index in flips for offset in range(k + 1)}
    components = list(parent.components)
    total = parent.total
    for index in affected:
        value = contribution(candidate, index, k=k, seed=seed)
        total += value - components[index]
        components[index] = value
    return Individual(candidate, tuple(components), total, parent.lineage)


def initial_island(slot: int, island_count: int) -> int:
    return slot % island_count


def visible(states: list[AgentState], island: int) -> list[AgentState]:
    return [state for state in states if state.island == island]


def rotate_champions(states: list[AgentState], island_count: int) -> None:
    champions = [
        max(
            visible(states, island),
            key=lambda state: (state.incumbent.score, state.agent_id),
        )
        for island in range(island_count)
    ]
    destinations = {
        champion.agent_id: (source + 1) % island_count for source, champion in enumerate(champions)
    }
    for state in states:
        if state.agent_id in destinations:
            state.island = destinations[state.agent_id]


def mean_hamming(states: list[AgentState]) -> float:
    candidates = [state.incumbent.candidate for state in states]
    distances = [
        sum(left != right for left, right in zip(candidates[i], candidates[j], strict=True))
        / len(candidates[i])
        for i in range(len(candidates))
        for j in range(i + 1, len(candidates))
    ]
    return statistics.fmean(distances)


def simulate(
    *,
    n: int,
    k: int,
    seed: str,
    condition: str,
    budget: int,
    imitation: float,
    policy_seed: int,
) -> dict[str, Any]:
    if budget < len(BASE_AGENT_IDS) or budget % len(BASE_AGENT_IDS):
        raise ValueError("budget must be a multiple of the eight-agent roster")
    island_count = ISLAND_COUNTS[condition]
    rng = random.Random(policy_seed)
    states = [
        AgentState(
            agent_id=agent_id,
            island=initial_island(slot, island_count),
            incumbent=make_individual(
                initial_candidate(agent_id, n),
                k=k,
                seed=seed,
                lineage=agent_id,
            ),
        )
        for slot, agent_id in enumerate(BASE_AGENT_IDS)
    ]
    best_attempt = max(state.incumbent.score for state in states)
    evaluations = len(states)
    adoption_attempts = 0
    accepted_adoptions = 0
    migrations = 0
    lineage_total = float(len(states))
    lineage_observations = 1
    migration_boundaries = {budget // 4, budget // 2, 3 * budget // 4}
    while evaluations < budget:
        state = states[evaluations % len(states)]
        peers = visible(states, state.island)
        champion = max(
            peers,
            key=lambda item: (item.incumbent.score, item.agent_id),
        )
        imitation_draw = rng.random()
        imitate = champion.agent_id != state.agent_id and imitation_draw < imitation
        parent = champion.incumbent if imitate else state.incumbent
        if imitate:
            adoption_attempts += 1
        child = mutate(parent, k=k, seed=seed, rng=rng)
        evaluations += 1
        best_attempt = max(best_attempt, child.score)
        if child.score > state.incumbent.score:
            if child.lineage != state.incumbent.lineage:
                accepted_adoptions += 1
            state.incumbent = child
        if evaluations in migration_boundaries and condition.startswith("multi_island_"):
            rotate_champions(states, island_count)
            migrations += 1
        lineage_total += len({item.incumbent.lineage for item in states})
        lineage_observations += 1
    return {
        "best_score": best_attempt,
        "final_diversity": mean_hamming(states),
        "final_lineages": len({state.incumbent.lineage for state in states}),
        "mean_active_lineages": lineage_total / lineage_observations,
        "adoption_attempts": adoption_attempts,
        "accepted_adoptions": accepted_adoptions,
        "migration_cycles": migrations,
    }


def random_reference(n: int, k: int, seed: str, *, samples: int = 512) -> dict[str, float]:
    rng_seed = int.from_bytes(
        hashlib.sha256(f"threshold-v3-reference:{k}:{seed}".encode()).digest()[:8],
        "big",
    )
    rng = random.Random(rng_seed)
    values = [
        make_individual(
            f"{rng.getrandbits(n):0{n}b}",
            k=k,
            seed=seed,
            lineage="random",
        ).score
        for _ in range(samples)
    ]
    return {"random_mean": statistics.fmean(values), "random_sd": statistics.pstdev(values)}


def _work_item(item: tuple[int, int, str, str, int, float, int]) -> dict[str, Any]:
    n, k, seed, condition, budget, imitation, policy_seed = item
    return {
        "k": k,
        "seed_sha256": hashlib.sha256(seed.encode()).hexdigest(),
        "condition": condition,
        "budget": budget,
        "imitation": imitation,
        "policy_seed": policy_seed,
        **simulate(
            n=n,
            k=k,
            seed=seed,
            condition=condition,
            budget=budget,
            imitation=imitation,
            policy_seed=policy_seed,
        ),
    }


def bootstrap_interval(values: list[float], label: str) -> tuple[float, float]:
    rng = random.Random(int.from_bytes(hashlib.sha256(label.encode()).digest()[:8], "big"))
    samples = sorted(statistics.fmean(rng.choice(values) for _ in values) for _ in range(10_000))
    return samples[250], samples[9750]


def summarize(
    rows: list[dict[str, Any]],
    references: dict[tuple[int, str], dict[str, float]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    indexed = {
        (
            int(row["k"]),
            str(row["seed_sha256"]),
            int(row["budget"]),
            float(row["imitation"]),
            int(row["policy_seed"]),
            str(row["condition"]),
        ): row
        for row in rows
    }
    output: list[dict[str, Any]] = []
    effect_values: dict[tuple[int, int, float, str], list[float]] = {}
    k_values = sorted({int(row["k"]) for row in rows})
    budgets = sorted({int(row["budget"]) for row in rows})
    imitation_levels = sorted({float(row["imitation"]) for row in rows})
    for k in k_values:
        for budget in budgets:
            for imitation in imitation_levels:
                pair_keys = sorted(
                    {
                        (str(row["seed_sha256"]), int(row["policy_seed"]))
                        for row in rows
                        if int(row["k"]) == k
                        and int(row["budget"]) == budget
                        and float(row["imitation"]) == imitation
                    }
                )
                for treatment, control in (
                    ("multi_island_4", "global_8"),
                    ("multi_island_4", "partition_4"),
                    ("multi_island_2", "global_8"),
                ):
                    z_values: list[float] = []
                    diversity_values: list[float] = []
                    lineage_values: list[float] = []
                    active_lineage_values: list[float] = []
                    for seed_hash, policy_seed in pair_keys:
                        left = indexed[(k, seed_hash, budget, imitation, policy_seed, treatment)]
                        right = indexed[(k, seed_hash, budget, imitation, policy_seed, control)]
                        z_values.append(
                            (float(left["best_score"]) - float(right["best_score"]))
                            / references[(k, seed_hash)]["random_sd"]
                        )
                        diversity_values.append(
                            float(left["final_diversity"]) - float(right["final_diversity"])
                        )
                        lineage_values.append(
                            float(left["final_lineages"]) - float(right["final_lineages"])
                        )
                        active_lineage_values.append(
                            float(left["mean_active_lineages"])
                            - float(right["mean_active_lineages"])
                        )
                    label = f"v3:{k}:{budget}:{imitation}:{treatment}:{control}"
                    low, high = bootstrap_interval(z_values, label)
                    effect_values[(k, budget, imitation, f"{treatment}-{control}")] = z_values
                    output.append(
                        {
                            "k": k,
                            "budget": budget,
                            "imitation": imitation,
                            "contrast": f"{treatment}_minus_{control}",
                            "paired_policy_runs": len(z_values),
                            "random_z_difference": statistics.fmean(z_values),
                            "random_z_ci_low": low,
                            "random_z_ci_high": high,
                            "win_rate": sum(value > 0 for value in z_values) / len(z_values),
                            "diversity_difference": statistics.fmean(diversity_values),
                            "lineage_count_difference": statistics.fmean(lineage_values),
                            "active_lineage_difference": statistics.fmean(active_lineage_values),
                        }
                    )

    passing: list[dict[str, int]] = []
    for row in output:
        if (
            int(row["k"]) == 0
            or float(row["imitation"]) != SELECTION_IMITATION
            or row["contrast"] != "multi_island_4_minus_global_8"
        ):
            row["phase_gate_passes"] = False
            continue
        k = int(row["k"])
        budget = int(row["budget"])
        rugged = effect_values[(k, budget, SELECTION_IMITATION, "multi_island_4-global_8")]
        smooth = effect_values[(0, budget, SELECTION_IMITATION, "multi_island_4-global_8")]
        interaction = [
            rugged_value - smooth_value
            for rugged_value, smooth_value in zip(rugged, smooth, strict=True)
        ]
        interaction_low, interaction_high = bootstrap_interval(
            interaction, f"v3-interaction:{k}:{budget}"
        )
        partition = next(
            item
            for item in output
            if int(item["k"]) == k
            and int(item["budget"]) == budget
            and float(item["imitation"]) == SELECTION_IMITATION
            and item["contrast"] == "multi_island_4_minus_partition_4"
        )
        row["rugged_minus_smooth_random_z"] = statistics.fmean(interaction)
        row["rugged_minus_smooth_random_z_ci_low"] = interaction_low
        row["rugged_minus_smooth_random_z_ci_high"] = interaction_high
        passes = (
            float(row["random_z_difference"]) >= RUGGED_EFFECT_FLOOR_Z
            and float(row["random_z_ci_low"]) > 0
            and statistics.fmean(interaction) >= INTERACTION_FLOOR_Z
            and interaction_low > 0
            and float(partition["random_z_difference"]) > 0
            and float(partition["random_z_ci_low"]) > 0
            and float(row["active_lineage_difference"]) >= 1
        )
        row["phase_gate_passes"] = passes
        if passes:
            passing.append({"k": k, "budget": budget})
    selected = min(passing, key=lambda item: (item["budget"], item["k"])) if passing else None
    return output, {
        "selection_imitation": SELECTION_IMITATION,
        "rugged_effect_floor_random_z": RUGGED_EFFECT_FLOOR_Z,
        "rugged_minus_smooth_floor_random_z": INTERACTION_FLOOR_Z,
        "passing_k_budget_cells": passing,
        "selection_rule": "earliest passing budget, then smallest K",
        "selected_rugged_k": selected["k"] if selected else None,
        "selected_anchor_budget": selected["budget"] if selected else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy-repetitions", type=int, default=4)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed-count", type=int, default=8)
    parser.add_argument("--k-values", nargs="+", type=int)
    parser.add_argument("--budgets", nargs="+", type=int)
    parser.add_argument("--imitation", nargs="+", type=float)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    landscape_data = json.loads(LANDSCAPES.read_text())
    n = int(landscape_data["n"])
    available_k = [int(value) for value in landscape_data["k_values"]]
    k_values = args.k_values or available_k
    budgets = args.budgets or list(BUDGETS)
    imitation_levels = args.imitation or list(IMITATION_LEVELS)
    seeds = [str(seed) for seed in landscape_data["seeds"][: args.seed_count]]
    if not seeds or any(value not in available_k for value in k_values):
        raise SystemExit("requested seeds/K values are outside the frozen calibration")
    if any(value not in BUDGETS for value in budgets):
        raise SystemExit("requested budget is not registered")
    if any(not 0 <= value <= 1 for value in imitation_levels):
        raise SystemExit("imitation levels must lie in [0, 1]")
    references = {
        (k, hashlib.sha256(seed.encode()).hexdigest()): random_reference(n, k, seed)
        for k in k_values
        for seed in seeds
    }
    items = [
        (n, k, seed, condition, budget, imitation, seed_index * 10_000 + repetition)
        for k in k_values
        for seed_index, seed in enumerate(seeds)
        for condition in CONDITIONS
        for budget in budgets
        for imitation in imitation_levels
        for repetition in range(args.policy_repetitions)
    ]
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(_work_item, items, chunksize=2))
    summary, decision = summarize(rows, references)
    payload = {
        "schema_version": 1,
        "method": "partial visible-champion imitation with actual move migration",
        "interpretation": "mechanism phase map, not an LLM performance forecast",
        "n": n,
        "k_values": k_values,
        "budgets": budgets,
        "imitation_levels": imitation_levels,
        "calibration_seed_count": len(seeds),
        "policy_repetitions": args.policy_repetitions,
        "migration_boundaries": [0.25, 0.5, 0.75],
        "decision": decision,
        "summary": summary,
    }
    rendered = json.dumps(payload, indent=2) + "\n"
    args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
