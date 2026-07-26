#!/usr/bin/env python3
"""Audit the difficulty constructs in the v6 extreme-hardness extension."""

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

from experiments.multi_island_hard import calibrate_threshold_v3_social as social
from experiments.multi_island_hard import run_threshold_v6_extreme_phase as phase

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "threshold_v6_extreme_construct_diagnostics_v2.json"
REGISTERED_NEIGHBOR_SAMPLES = 256
MIN_EXTREME_BLOCK_SEPARATION = 54
MIN_MEAN_EXTREME_SEPARATION = 0.55
MAX_HIGHEST_K_AUTOCORRELATION = 0.15


@dataclass(frozen=True)
class WorkItem:
    block: int
    k: int
    seed: str
    samples: int


def correlation(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("correlation requires paired samples")
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    covariance = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_variance = sum((value - left_mean) ** 2 for value in left)
    right_variance = sum((value - right_mean) ** 2 for value in right)
    if not left_variance or not right_variance:
        raise ValueError("degenerate neighbour sample")
    return covariance / (left_variance * right_variance) ** 0.5


def flip(candidate: str, index: int) -> str:
    replacement = "1" if candidate[index] == "0" else "0"
    return candidate[:index] + replacement + candidate[index + 1 :]


def diagnose_rugged(item: WorkItem) -> dict[str, Any]:
    rng_seed = int.from_bytes(
        hashlib.sha256(
            f"threshold-v6-extreme-construct:{item.block}:{item.k}:{item.seed}".encode()
        ).digest()[:8],
        "big",
    )
    rng = random.Random(rng_seed)
    base_scores: list[float] = []
    neighbour_scores: list[float] = []
    for _ in range(item.samples):
        candidate = f"{rng.getrandbits(phase.RUGGED_N):0{phase.RUGGED_N}b}"
        individual = social.make_individual(
            candidate, k=item.k, seed=item.seed, lineage="construct"
        )
        bit = rng.randrange(phase.RUGGED_N)
        neighbour = flip(candidate, bit)
        affected = {(bit - offset) % phase.RUGGED_N for offset in range(item.k + 1)}
        neighbour_total = individual.total + sum(
            social.contribution(neighbour, index, k=item.k, seed=item.seed)
            - individual.components[index]
            for index in affected
        )
        base_scores.append(individual.score)
        neighbour_scores.append(neighbour_total / phase.RUGGED_N)
    random_sd = statistics.pstdev(base_scores)
    deltas = [right - left for left, right in zip(base_scores, neighbour_scores, strict=True)]
    if random_sd <= 0:
        raise ValueError("Rugged random sample has zero variance")
    return {
        "block": item.block,
        "k": item.k,
        "seed_sha256": phase.seed_sha256(item.seed),
        "samples": item.samples,
        "affected_fraction": (item.k + 1) / phase.RUGGED_N,
        "one_bit_autocorrelation": correlation(base_scores, neighbour_scores),
        "mean_absolute_neighbour_delta_random_z": statistics.fmean(abs(value) for value in deltas)
        / random_sd,
        "neighbour_delta_sd_random_z": statistics.pstdev(deltas) / random_sd,
    }


def registered_configuration(*, blocks: int, samples: int) -> bool:
    return blocks == phase.REGISTERED_BLOCKS and samples == REGISTERED_NEIGHBOR_SAMPLES


def smooth_scale_rows() -> list[dict[str, Any]]:
    return [
        {
            "n": n,
            "budget": budget,
            "budget_over_n_squared": budget / (n * n),
            "uniform_one_bit_first_mismatch_probability": 1 / n,
            "strict_one_bit_local_optima": 1,
            "unique_global_optimum": True,
        }
        for n in phase.SMOOTH_SIZES
        for budget in phase.BUDGETS
    ]


def aggregate_rugged(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for k in phase.RUGGED_K_VALUES:
        selected = [row for row in rows if int(row["k"]) == k]
        output.append(
            {
                "k": k,
                "affected_fraction": (k + 1) / phase.RUGGED_N,
                "blocks": len(selected),
                "mean_one_bit_autocorrelation": statistics.fmean(
                    float(row["one_bit_autocorrelation"]) for row in selected
                ),
                "mean_absolute_neighbour_delta_random_z": statistics.fmean(
                    float(row["mean_absolute_neighbour_delta_random_z"]) for row in selected
                ),
                "mean_neighbour_delta_sd_random_z": statistics.fmean(
                    float(row["neighbour_delta_sd_random_z"]) for row in selected
                ),
            }
        )
    return output


def audit(payload: dict[str, Any], *, require_registered: bool) -> list[str]:
    errors: list[str] = []
    blocks = int(payload.get("blocks", 0))
    samples = int(payload.get("neighbour_samples_per_block_k", 0))
    if payload.get("schema_version") != 1:
        errors.append("unexpected schema version")
    if require_registered and not payload.get("fully_registered_run"):
        errors.append("construct diagnostic is not the fully registered run")
    if require_registered and not registered_configuration(blocks=blocks, samples=samples):
        errors.append("registered construct grid drifted")
    expected = {(block, k) for block in range(blocks) for k in phase.RUGGED_K_VALUES}
    observed: set[tuple[int, int]] = set()
    for row in payload.get("rugged_landscapes", []):
        key = (int(row.get("block")), int(row.get("k")))
        if key in observed:
            errors.append(f"duplicate Rugged construct row: {key}")
        observed.add(key)
        block, k = key
        if row.get("seed_sha256") != phase.seed_sha256(phase.phase_seed(block)):
            errors.append(f"unexpected seed hash: {key}")
        if int(row.get("samples", 0)) != samples:
            errors.append(f"sample count drifted: {key}")
        correlation_value = row.get("one_bit_autocorrelation")
        if (
            not isinstance(correlation_value, (int, float))
            or not -1 <= float(correlation_value) <= 1
        ):
            errors.append(f"invalid autocorrelation: {key}")
        if abs(float(row.get("affected_fraction", -1)) - (k + 1) / phase.RUGGED_N) > 1e-12:
            errors.append(f"affected fraction drifted: {key}")
        for field in ("mean_absolute_neighbour_delta_random_z", "neighbour_delta_sd_random_z"):
            value = row.get(field)
            if not isinstance(value, (int, float)) or float(value) <= 0:
                errors.append(f"invalid {field}: {key}")
    if observed != expected:
        errors.append(
            f"Rugged construct matrix mismatch: missing={len(expected - observed)}, extra={len(observed - expected)}"
        )
    if payload.get("smooth_scale") != smooth_scale_rows():
        errors.append("Smooth analytic scale drifted")
    return errors


def construct_gates(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload["rugged_landscapes"]
    aggregate = aggregate_rugged(rows)
    correlations = [float(row["mean_one_bit_autocorrelation"]) for row in aggregate]
    extremes = {
        block: {
            int(row["k"]): float(row["one_bit_autocorrelation"])
            for row in rows
            if int(row["block"]) == block
        }
        for block in range(int(payload["blocks"]))
    }
    separated_blocks = sum(
        values[phase.RUGGED_K_VALUES[-1]] < values[phase.RUGGED_K_VALUES[0]]
        for values in extremes.values()
    )
    mean_separation = correlations[0] - correlations[-1]
    rugged_monotone = all(left > right for left, right in zip(correlations, correlations[1:]))
    highest_is_extreme = correlations[-1] <= MAX_HIGHEST_K_AUTOCORRELATION
    rugged_extremes_separate = bool(
        separated_blocks >= MIN_EXTREME_BLOCK_SEPARATION
        and mean_separation >= MIN_MEAN_EXTREME_SEPARATION
        and highest_is_extreme
    )
    smooth_ratios = [float(row["budget_over_n_squared"]) for row in payload["smooth_scale"]]
    smooth_is_uniformly_hard = max(smooth_ratios) <= 0.02
    bridge_delta = abs((phase.RUGGED_K_VALUES[0] + 1) / phase.RUGGED_N - (128 + 1) / 512)
    bridge_matches_v6_boundary = bridge_delta <= 0.01
    return {
        "smooth_all_budget_over_n_squared_at_most_0_02": smooth_is_uniformly_hard,
        "rugged_mean_autocorrelation_strictly_decreases_with_k": rugged_monotone,
        "rugged_extreme_separated_blocks": separated_blocks,
        "rugged_extreme_separated_blocks_required": MIN_EXTREME_BLOCK_SEPARATION,
        "rugged_mean_lowest_minus_highest_k_autocorrelation": mean_separation,
        "rugged_mean_extreme_separation_required": MIN_MEAN_EXTREME_SEPARATION,
        "rugged_highest_k_mean_autocorrelation": correlations[-1],
        "rugged_highest_k_max_autocorrelation": MAX_HIGHEST_K_AUTOCORRELATION,
        "rugged_extremes_separate": rugged_extremes_separate,
        "lowest_extreme_affected_fraction_delta_from_v6_boundary": bridge_delta,
        "lowest_extreme_affected_fraction_bridges_v6": bridge_matches_v6_boundary,
        "construct_validity_passes": bool(
            smooth_is_uniformly_hard
            and rugged_monotone
            and rugged_extremes_separate
            and bridge_matches_v6_boundary
        ),
    }


def run_diagnostics(*, blocks: int, samples: int, max_workers: int) -> dict[str, Any]:
    seeds = tuple(phase.phase_seed(block) for block in range(blocks))
    phase.validate_seed_isolation(seeds)
    items = [
        WorkItem(block, k, seeds[block], samples)
        for block in range(blocks)
        for k in phase.RUGGED_K_VALUES
    ]
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as pool:
        rugged = list(pool.map(diagnose_rugged, items, chunksize=1))
    payload: dict[str, Any] = {
        "schema_version": 1,
        "purpose": "topology-independent construct audit of the extreme-hardness extension",
        "fully_registered_run": registered_configuration(blocks=blocks, samples=samples),
        "blocks": blocks,
        "neighbour_samples_per_block_k": samples,
        "smooth_scale": smooth_scale_rows(),
        "rugged_landscapes": sorted(rugged, key=lambda row: (row["block"], row["k"])),
        "interpretation_limit": (
            "These diagnostics establish only that the extension reaches much lower local "
            "correlation. They contain no topology outcome."
        ),
    }
    payload["rugged_summary"] = aggregate_rugged(payload["rugged_landscapes"])
    payload["construct_gates"] = construct_gates(payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blocks", type=int, default=phase.REGISTERED_BLOCKS)
    parser.add_argument("--samples", type=int, default=REGISTERED_NEIGHBOR_SAMPLES)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-reduced", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.blocks < 2 or args.samples < 16 or args.max_workers < 1:
        raise SystemExit("invalid extreme construct configuration")
    registered = registered_configuration(blocks=args.blocks, samples=args.samples)
    if not registered and (not args.allow_reduced or args.output == DEFAULT_OUTPUT):
        raise SystemExit(
            "reduced construct diagnostics require --allow-reduced and a non-default output"
        )
    payload = run_diagnostics(
        blocks=args.blocks, samples=args.samples, max_workers=args.max_workers
    )
    errors = audit(payload, require_registered=registered)
    if errors:
        raise SystemExit("construct audit failed: " + "; ".join(errors))
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload["construct_gates"], indent=2))
    if registered and not payload["construct_gates"]["construct_validity_passes"]:
        raise SystemExit("registered extreme construct-validity gates failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
