#!/usr/bin/env python3
"""Run the held-out extreme-hardness extension of the v6 phase map.

The original v6 grid reaches K/N ~= 0.25.  This independent extension keeps
that ratio as a bridge and continues to K/N ~= 0.94.  Rugged scores are never
pooled across dimensions or landscapes; all topology contrasts remain paired
within one landscape-policy block.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import calibrate_threshold_v3_social as social
from experiments.multi_island_hard import calibrate_threshold_v5_hard_smooth as v5
from experiments.multi_island_hard import run_threshold_v6_phase_map as v6

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "threshold_v6_extreme_phase_raw.json"

SMOOTH_SIZES = (2048, 4096, 8192)
RUGGED_N = 128
RUGGED_K_VALUES = (32, 64, 96, 120)
BUDGETS = (16384, 32768, 65536)
CONDITIONS = v6.CONDITIONS
REGISTERED_BLOCKS = 24
REGISTERED_REFERENCE_SAMPLES = 512
MUTATION_POLICY = v6.MUTATION_POLICY
INITIAL_SALT = "coral-threshold-v6-extreme-phase"


@dataclass(frozen=True)
class WorkItem:
    family: str
    difficulty: int
    budget: int
    block: int
    seed: str
    policy_seed: int
    condition: str


@dataclass(frozen=True)
class CompactSmoothIndividual:
    """Permuted-LeadingOnes state represented in hidden-order coordinates."""

    mismatch_mask: int
    n: int
    lineage: str

    @property
    def prefix(self) -> int:
        if not self.mismatch_mask:
            return self.n
        return (self.mismatch_mask & -self.mismatch_mask).bit_length() - 1

    @property
    def score(self) -> float:
        return self.prefix / self.n


def phase_seed(block: int) -> str:
    return hashlib.sha256(f"threshold-v6-extreme-phase-heldout:{block}".encode()).hexdigest()


def phase_policy_seed(block: int) -> int:
    return int.from_bytes(
        hashlib.sha256(f"threshold-v6-extreme-phase-policy:{block}".encode()).digest()[:8],
        "big",
    )


def seed_sha256(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def prior_seed_hashes() -> set[str]:
    hashes = v6.prior_seed_hashes()
    hashes.update(v6.seed_sha256(v6.phase_seed(block)) for block in range(v6.REGISTERED_BLOCKS))
    return hashes


def validate_seed_isolation(seeds: tuple[str, ...]) -> None:
    hashes = [seed_sha256(seed) for seed in seeds]
    if len(set(hashes)) != len(hashes):
        raise ValueError("extreme phase-map seeds are not unique")
    overlap = set(hashes) & prior_seed_hashes()
    if overlap:
        raise ValueError(f"extreme phase-map seeds overlap prior data: {sorted(overlap)}")


def make_compact_smooth(
    candidate: str,
    *,
    target: str,
    order: tuple[int, ...],
    lineage: str,
) -> tuple[CompactSmoothIndividual, tuple[int, ...]]:
    rank_by_coordinate = [0] * len(candidate)
    mismatch_mask = 0
    for rank, coordinate in enumerate(order):
        rank_by_coordinate[coordinate] = rank
        if candidate[coordinate] != target[coordinate]:
            mismatch_mask |= 1 << rank
    return (
        CompactSmoothIndividual(mismatch_mask, len(candidate), lineage),
        tuple(rank_by_coordinate),
    )


def mutate_compact_smooth(
    parent: CompactSmoothIndividual,
    *,
    rank_by_coordinate: tuple[int, ...],
    rng: random.Random,
) -> CompactSmoothIndividual:
    mismatch_mask = parent.mismatch_mask
    for coordinate in social.mutation_indices(rng, parent.n, MUTATION_POLICY):
        mismatch_mask ^= 1 << rank_by_coordinate[coordinate]
    return CompactSmoothIndividual(mismatch_mask, parent.n, parent.lineage)


def simulate_smooth(item: WorkItem) -> dict[str, Any]:
    n = item.difficulty
    target = v5.hidden_target(item.seed, n)
    order = v5.hidden_coordinate_order(item.seed, n)
    island_count = social.ISLAND_COUNTS[item.condition]
    rng = random.Random(item.policy_seed)
    states: list[social.AgentState] = []
    rank_by_coordinate: tuple[int, ...] | None = None
    for slot, agent_id in enumerate(social.BASE_AGENT_IDS):
        individual, ranks = make_compact_smooth(
            social.initial_candidate(agent_id, n, INITIAL_SALT),
            target=target,
            order=order,
            lineage=agent_id,
        )
        if rank_by_coordinate is None:
            rank_by_coordinate = ranks
        elif ranks != rank_by_coordinate:
            raise RuntimeError("hidden coordinate ranks drifted across agents")
        states.append(
            social.AgentState(
                agent_id=agent_id,
                island=social.initial_island(slot, island_count),
                incumbent=individual,
            )
        )
    if rank_by_coordinate is None:
        raise RuntimeError("empty agent roster")
    best_prefix = max(state.incumbent.prefix for state in states)
    evaluations = len(states)
    migration_boundaries = {item.budget // 4, item.budget // 2, 3 * item.budget // 4}
    while evaluations < item.budget:
        state = states[evaluations % len(states)]
        champion = max(
            social.visible(states, state.island),
            key=lambda peer: (peer.incumbent.score, peer.agent_id),
        )
        imitation_draw = rng.random()
        imitate = champion.agent_id != state.agent_id and imitation_draw < 1.0
        parent = champion.incumbent if imitate else state.incumbent
        child = mutate_compact_smooth(
            parent,
            rank_by_coordinate=rank_by_coordinate,
            rng=rng,
        )
        evaluations += 1
        best_prefix = max(best_prefix, child.prefix)
        if child.score > state.incumbent.score:
            state.incumbent = child
        if evaluations in migration_boundaries and item.condition == "multi_island_4":
            social.rotate_champions(states, island_count, "elite")
    return {
        "best_score": best_prefix / n,
        "best_prefix": best_prefix,
        "exact": best_prefix == n,
    }


def run_item(item: WorkItem) -> tuple[WorkItem, dict[str, Any]]:
    if item.family == "smooth":
        return item, simulate_smooth(item)
    if item.family != "rugged":
        raise ValueError(f"unknown extreme phase-map family: {item.family}")
    result = social.simulate(
        n=RUGGED_N,
        k=item.difficulty,
        seed=item.seed,
        condition=item.condition,
        budget=item.budget,
        imitation=1.0,
        policy_seed=item.policy_seed,
        mutation_policy=MUTATION_POLICY,
        migration_selection="elite",
        initial_salt=INITIAL_SALT,
    )
    return item, {"best_score": float(result["best_score"])}


def registered_configuration(
    *,
    smooth_sizes: tuple[int, ...],
    rugged_ks: tuple[int, ...],
    budgets: tuple[int, ...],
    blocks: int,
    reference_samples: int,
) -> bool:
    return bool(
        smooth_sizes == SMOOTH_SIZES
        and rugged_ks == RUGGED_K_VALUES
        and budgets == BUDGETS
        and blocks == REGISTERED_BLOCKS
        and reference_samples == REGISTERED_REFERENCE_SAMPLES
    )


def run_phase_map(
    *,
    smooth_sizes: tuple[int, ...],
    rugged_ks: tuple[int, ...],
    budgets: tuple[int, ...],
    blocks: int,
    reference_samples: int,
    max_workers: int,
) -> dict[str, Any]:
    seeds = tuple(phase_seed(block) for block in range(blocks))
    validate_seed_isolation(seeds)
    items = [
        WorkItem(
            family, difficulty, budget, block, seeds[block], phase_policy_seed(block), condition
        )
        for family, difficulties in (("smooth", smooth_sizes), ("rugged", rugged_ks))
        for difficulty in difficulties
        for budget in budgets
        for block in range(blocks)
        for condition in CONDITIONS
    ]
    grouped: dict[tuple[str, int, int, int], dict[str, dict[str, Any]]] = {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as pool:
        for item, result in pool.map(run_item, items, chunksize=1):
            key = (item.family, item.difficulty, item.budget, item.block)
            grouped.setdefault(key, {})[item.condition] = result

    rows = []
    for (family, difficulty, budget, block), scores in sorted(grouped.items()):
        if set(scores) != set(CONDITIONS):
            raise RuntimeError(
                f"incomplete topology triplet: {(family, difficulty, budget, block)}"
            )
        rows.append(
            {
                "family": family,
                "n": difficulty if family == "smooth" else RUGGED_N,
                "k": 0 if family == "smooth" else difficulty,
                "budget": budget,
                "block": block,
                "seed_sha256": seed_sha256(seeds[block]),
                "policy_seed_sha256": hashlib.sha256(
                    str(phase_policy_seed(block)).encode()
                ).hexdigest(),
                "conditions": scores,
            }
        )
    references = [
        {
            "k": k,
            "block": block,
            "seed_sha256": seed_sha256(seeds[block]),
            **social.random_reference(RUGGED_N, k, seeds[block], samples=reference_samples),
        }
        for k in rugged_ks
        for block in range(blocks)
    ]
    registered = registered_configuration(
        smooth_sizes=smooth_sizes,
        rugged_ks=rugged_ks,
        budgets=budgets,
        blocks=blocks,
        reference_samples=reference_samples,
    )
    return {
        "schema_version": 1,
        "purpose": "held-out extreme Smooth and normalized-Rugged topology phase map",
        "fully_registered_run": registered,
        "families": {
            "smooth": "hidden-target hidden-order Permuted LeadingOnes",
            "rugged": "adjacent hidden-seed NK",
        },
        "smooth_sizes": list(smooth_sizes),
        "rugged_n": RUGGED_N,
        "rugged_k_values": list(rugged_ks),
        "rugged_affected_fractions": [(k + 1) / RUGGED_N for k in rugged_ks],
        "budgets": list(budgets),
        "conditions": list(CONDITIONS),
        "mutation_policy": MUTATION_POLICY,
        "imitation": 1.0,
        "migration": "three move-not-copy elite rotations at B/4, B/2, 3B/4",
        "blocks": blocks,
        "inference_unit": "paired landscape-policy block",
        "reference_samples_per_rugged_block": reference_samples,
        "prior_seed_overlap": False,
        "rows": rows,
        "rugged_random_references": references,
        "interpretation_limit": (
            "This maps a frozen scripted mechanism beyond the original v6 ruggedness boundary. "
            "It does not establish natural-agent, CORAL-anchor, or real-task validity."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--smooth-sizes", type=int, nargs="+", default=list(SMOOTH_SIZES))
    parser.add_argument("--rugged-ks", type=int, nargs="+", default=list(RUGGED_K_VALUES))
    parser.add_argument("--budgets", type=int, nargs="+", default=list(BUDGETS))
    parser.add_argument("--blocks", type=int, default=REGISTERED_BLOCKS)
    parser.add_argument("--reference-samples", type=int, default=REGISTERED_REFERENCE_SAMPLES)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--allow-reduced", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    smooth_sizes = tuple(sorted(set(args.smooth_sizes)))
    rugged_ks = tuple(sorted(set(args.rugged_ks)))
    budgets = tuple(sorted(set(args.budgets)))
    invalid = bool(
        not smooth_sizes
        or not rugged_ks
        or not budgets
        or min(smooth_sizes) < 8
        or min(rugged_ks) < 1
        or max(rugged_ks) >= RUGGED_N
        or min(budgets) < len(social.BASE_AGENT_IDS)
        or any(budget % len(social.BASE_AGENT_IDS) for budget in budgets)
        or args.blocks < 2
        or args.reference_samples < 16
        or args.max_workers < 1
    )
    if invalid:
        raise SystemExit("invalid extreme phase-map configuration")
    registered = registered_configuration(
        smooth_sizes=smooth_sizes,
        rugged_ks=rugged_ks,
        budgets=budgets,
        blocks=args.blocks,
        reference_samples=args.reference_samples,
    )
    if not registered and (not args.allow_reduced or args.output == DEFAULT_OUTPUT):
        raise SystemExit(
            "reduced extreme phase maps require --allow-reduced and a non-default output"
        )
    payload = run_phase_map(
        smooth_sizes=smooth_sizes,
        rugged_ks=rugged_ks,
        budgets=budgets,
        blocks=args.blocks,
        reference_samples=args.reference_samples,
        max_workers=args.max_workers,
    )
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(
        json.dumps(
            {
                "fully_registered_run": payload["fully_registered_run"],
                "topology_triplets": len(payload["rows"]),
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
