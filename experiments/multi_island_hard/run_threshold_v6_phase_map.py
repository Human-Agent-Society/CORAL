#!/usr/bin/env python3
"""Run a preregistered held-out hardness-response map in the fast simulator.

This experiment is deliberately separate from the v4/v5 calibration seeds.
It maps task difficulty instead of selecting one favorable anchor: Smooth is
scaled by Permuted-LeadingOnes length, while Rugged is scaled by adjacent-NK
epistasis.  The expensive CORAL runs remain an implementation/anchor check;
this simulator is the only practical way to estimate the full response
surface with enough independent landscape-policy blocks.
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

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "threshold_v6_phase_map_raw.json"
V4_CALIBRATION = ROOT / "threshold_v4_scale_calibration.json"
TASKDATA = ROOT / "tasks/institutional_landscape/taskdata"

SMOOTH_SIZES = (128, 256, 512, 1024, 2048)
RUGGED_N = 512
RUGGED_K_VALUES = (8, 16, 32, 64, 128)
BUDGETS = (2048, 4096, 8192, 16384, 32768)
CONDITIONS = ("global_8", "partition_4", "multi_island_4")
REGISTERED_BLOCKS = 24
REGISTERED_REFERENCE_SAMPLES = 256
MUTATION_POLICY = "registered_mixed"
INITIAL_SALT = "coral-threshold-v6-phase-map"


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
class SmoothIndividual:
    candidate: str
    prefix: int
    lineage: str

    @property
    def score(self) -> float:
        return self.prefix / len(self.candidate)


def phase_seed(block: int) -> str:
    return hashlib.sha256(f"threshold-v6-phase-heldout:{block}".encode()).hexdigest()


def phase_policy_seed(block: int) -> int:
    return int.from_bytes(
        hashlib.sha256(f"threshold-v6-phase-policy:{block}".encode()).digest()[:8],
        "big",
    )


def seed_sha256(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def prior_seed_hashes() -> set[str]:
    hashes: set[str] = set()
    calibration = json.loads(V4_CALIBRATION.read_text())
    hashes.update(str(value) for value in calibration["calibration_seed_sha256"])
    for path in TASKDATA.glob("*_replicated_v5.json"):
        payload = json.loads(path.read_text())
        hashes.update(seed_sha256(str(seed)) for seed in payload.get("seeds", []))
    return hashes


def validate_seed_isolation(seeds: tuple[str, ...]) -> None:
    hashes = [seed_sha256(seed) for seed in seeds]
    if len(set(hashes)) != len(hashes):
        raise ValueError("v6 phase-map seeds are not unique")
    overlap = set(hashes) & prior_seed_hashes()
    if overlap:
        raise ValueError(f"v6 phase-map seeds overlap prior data: {sorted(overlap)}")


def make_smooth_individual(
    candidate: str,
    *,
    target: str,
    order: tuple[int, ...],
    lineage: str,
) -> SmoothIndividual:
    return SmoothIndividual(
        candidate=candidate,
        prefix=v5.leading_ones(candidate, target, order),
        lineage=lineage,
    )


def mutate_smooth(
    parent: SmoothIndividual,
    *,
    target: str,
    order: tuple[int, ...],
    rng: random.Random,
) -> SmoothIndividual:
    bits = list(parent.candidate)
    for index in social.mutation_indices(rng, len(bits), MUTATION_POLICY):
        bits[index] = "0" if bits[index] == "1" else "1"
    return make_smooth_individual(
        "".join(bits),
        target=target,
        order=order,
        lineage=parent.lineage,
    )


def simulate_smooth(item: WorkItem) -> dict[str, Any]:
    n = item.difficulty
    target = v5.hidden_target(item.seed, n)
    order = v5.hidden_coordinate_order(item.seed, n)
    island_count = social.ISLAND_COUNTS[item.condition]
    rng = random.Random(item.policy_seed)
    states = [
        social.AgentState(
            agent_id=agent_id,
            island=social.initial_island(slot, island_count),
            incumbent=make_smooth_individual(
                social.initial_candidate(agent_id, n, INITIAL_SALT),
                target=target,
                order=order,
                lineage=agent_id,
            ),
        )
        for slot, agent_id in enumerate(social.BASE_AGENT_IDS)
    ]
    best_prefix = max(state.incumbent.prefix for state in states)
    evaluations = len(states)
    migration_boundaries = {item.budget // 4, item.budget // 2, 3 * item.budget // 4}
    while evaluations < item.budget:
        state = states[evaluations % len(states)]
        champion = max(
            social.visible(states, state.island),
            key=lambda peer: (peer.incumbent.score, peer.agent_id),
        )
        # Match social.simulate at imitation=1.0, including RNG consumption.
        imitation_draw = rng.random()
        imitate = champion.agent_id != state.agent_id and imitation_draw < 1.0
        parent = champion.incumbent if imitate else state.incumbent
        child = mutate_smooth(parent, target=target, order=order, rng=rng)
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
        raise ValueError(f"unknown phase-map family: {item.family}")
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
        WorkItem(family, difficulty, budget, block, seeds[block], phase_policy_seed(block), condition)
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

    rows: list[dict[str, Any]] = []
    for (family, difficulty, budget, block), scores in sorted(grouped.items()):
        if set(scores) != set(CONDITIONS):
            raise RuntimeError(f"incomplete topology triplet: {(family, difficulty, budget, block)}")
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
            **social.random_reference(
                RUGGED_N,
                k,
                seeds[block],
                samples=reference_samples,
            ),
        }
        for k in rugged_ks
        for block in range(blocks)
    ]
    fully_registered = registered_configuration(
        smooth_sizes=smooth_sizes,
        rugged_ks=rugged_ks,
        budgets=budgets,
        blocks=blocks,
        reference_samples=reference_samples,
    )
    return {
        "schema_version": 1,
        "purpose": "held-out Smooth-size and Rugged-epistasis topology phase map",
        "fully_registered_run": fully_registered,
        "families": {
            "smooth": "hidden-target hidden-order Permuted LeadingOnes",
            "rugged": "adjacent hidden-seed NK",
        },
        "smooth_sizes": list(smooth_sizes),
        "rugged_n": RUGGED_N,
        "rugged_k_values": list(rugged_ks),
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
            "This maps a scripted mechanism. It cannot establish natural-agent or "
            "real-task validity, and it cannot replace the CORAL anchor audit."
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
    if (
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
    ):
        raise SystemExit("invalid phase-map configuration")
    registered = registered_configuration(
        smooth_sizes=smooth_sizes,
        rugged_ks=rugged_ks,
        budgets=budgets,
        blocks=args.blocks,
        reference_samples=args.reference_samples,
    )
    if not registered and (not args.allow_reduced or args.output == DEFAULT_OUTPUT):
        raise SystemExit("reduced phase maps require --allow-reduced and a non-default output")
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
