#!/usr/bin/env python3
"""Freeze held-out v5 difficulty diagnostics independently of topology outcomes."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import random
import statistics
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import calibrate_threshold_v5_hard_smooth as smooth
from experiments.multi_island_hard import diagnose_threshold_v2 as nk
from experiments.multi_island_hard import run_threshold_v5_mechanism as runner

ROOT = Path(__file__).resolve().parent
TASKDATA = ROOT / "tasks/institutional_landscape/taskdata"
DEFAULT_OUTPUT = ROOT / "threshold_v5_diagnostics.json"
REGISTERED_RANDOM_SAMPLES = 1024
REGISTERED_GREEDY_STARTS = 32
MIN_RUGGED_UNIQUE_MAXIMA = 24


def correlation(left: list[float], right: list[float]) -> float:
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    covariance = sum(
        (x - left_mean) * (y - right_mean)
        for x, y in zip(left, right, strict=True)
    )
    left_variance = sum((value - left_mean) ** 2 for value in left)
    right_variance = sum((value - right_mean) ** 2 for value in right)
    if left_variance == 0 or right_variance == 0:
        return 0.0
    return covariance / (left_variance * right_variance) ** 0.5


def smooth_diagnostic(
    task: str,
    seed_index: int,
    seed: str,
    *,
    n: int,
    samples: int,
    starts: int,
) -> dict[str, Any]:
    """Diagnose Permuted LeadingOnes without pretending an oracle is an agent."""

    rng_seed = int.from_bytes(
        hashlib.sha256(f"threshold-v5-diagnostics:{task}:{seed}".encode()).digest()[:8],
        "big",
    )
    rng = random.Random(rng_seed)
    target = smooth.hidden_target(seed, n)
    order = smooth.hidden_coordinate_order(seed, n)
    candidates = [nk.random_candidate(rng, n) for _ in range(samples)]
    prefixes = [smooth.leading_ones(item, target, order) for item in candidates]
    neighbor_prefixes = [
        smooth.leading_ones(nk.flip(item, rng.randrange(n)), target, order)
        for item in candidates
    ]
    oracle_starts = [nk.random_candidate(rng, n) for _ in range(starts)]
    # A strict improving oracle flips the current first mismatch. It reaches
    # the unique target in exactly the initial Hamming distance. This proves
    # topology, not black-box tractability; the latter is measured by the
    # separately frozen registered-policy calibration.
    oracle_steps = [
        sum(left != right for left, right in zip(item, target, strict=True))
        for item in oracle_starts
    ]
    scores = [prefix / n for prefix in prefixes]
    neighbor_scores = [prefix / n for prefix in neighbor_prefixes]
    zero_prefix = smooth.leading_ones("0" * n, target, order)
    return {
        "task": task,
        "family": "permuted_leading_ones",
        "seed_index": seed_index,
        "seed_sha256": hashlib.sha256(seed.encode()).hexdigest(),
        "n": n,
        "k": 0,
        "random_sample_count": samples,
        "random_mean": statistics.fmean(scores),
        "random_sd": statistics.pstdev(scores),
        "random_best": max(scores),
        "zero_candidate_score": zero_prefix / n,
        "one_bit_autocorrelation": correlation(scores, neighbor_scores),
        "greedy_start_count": starts,
        "greedy_unique_maxima": 1,
        "greedy_reference_score": 1.0,
        "greedy_mean_steps": statistics.fmean(oracle_steps),
        "reference_is_exact": True,
        "strict_one_bit_local_optima": 1,
        "unique_global_optimum": True,
        "oracle_note": (
            "The exact improving-coordinate oracle diagnoses topology only; "
            "it is hidden from participants and is not a performance baseline."
        ),
    }


def rugged_diagnostic(
    item: tuple[str, int, str, int, int, int, int],
) -> dict[str, Any]:
    task, seed_index, seed, n, k, samples, starts = item
    row = nk.diagnose_seed(
        task,
        seed_index,
        seed,
        n=n,
        k=k,
        samples=samples,
        starts=starts,
    )
    row["family"] = "nk"
    return row


def selected_bundles() -> tuple[dict[str, Any], dict[str, Any]]:
    selection = runner.registered_selection()
    smooth_bundle = json.loads(
        (TASKDATA / "smooth512_permuted_leading_ones_replicated_v5.json").read_text()
    )
    rugged_bundle = json.loads(
        (TASKDATA / f"rugged512_k{selection['k']}_replicated_v5.json").read_text()
    )
    if smooth_bundle["seeds"] != rugged_bundle["seeds"]:
        raise ValueError("v5 Smooth and Rugged diagnostics require paired held-out seeds")
    return smooth_bundle, rugged_bundle


def difficulty_gates(rows: list[dict[str, Any]], *, starts: int) -> dict[str, Any]:
    smooth_rows = [row for row in rows if row["family"] == "permuted_leading_ones"]
    rugged_rows = [row for row in rows if row["family"] == "nk"]
    paired = bool(
        len(smooth_rows) == len(rugged_rows) == 8
        and [row["seed_sha256"] for row in smooth_rows]
        == [row["seed_sha256"] for row in rugged_rows]
    )
    smooth_topology = bool(
        smooth_rows
        and all(
            row["reference_is_exact"]
            and row["greedy_unique_maxima"] == 1
            and row["strict_one_bit_local_optima"] == 1
            and row["unique_global_optimum"]
            for row in smooth_rows
        )
    )
    rugged_multibasin = bool(
        rugged_rows
        and starts >= REGISTERED_GREEDY_STARTS
        and all(
            int(row["greedy_unique_maxima"]) >= MIN_RUGGED_UNIQUE_MAXIMA
            and not row["reference_is_exact"]
            for row in rugged_rows
        )
    )
    autocorrelation_separation = bool(
        smooth_rows
        and rugged_rows
        and max(float(row["one_bit_autocorrelation"]) for row in rugged_rows)
        < min(float(row["one_bit_autocorrelation"]) for row in smooth_rows)
    )
    return {
        "paired_heldout_seeds": paired,
        "smooth_unique_one_bit_optimum": smooth_topology,
        "rugged_minimum_unique_maxima": MIN_RUGGED_UNIQUE_MAXIMA,
        "rugged_multibasin": rugged_multibasin,
        "one_bit_autocorrelation_separates_families": autocorrelation_separation,
        "heldout_difficulty_passes": bool(
            paired and smooth_topology and rugged_multibasin and autocorrelation_separation
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=REGISTERED_RANDOM_SAMPLES)
    parser.add_argument("--starts", type=int, default=REGISTERED_GREEDY_STARTS)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-reduced", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.samples < 128 or args.starts < 2 or args.max_workers < 1:
        raise SystemExit("invalid v5 diagnostic reduction")
    registered = (
        args.samples == REGISTERED_RANDOM_SAMPLES
        and args.starts == REGISTERED_GREEDY_STARTS
    )
    if not registered and (not args.allow_reduced or args.output == DEFAULT_OUTPUT):
        raise SystemExit("reduced diagnostics require --allow-reduced and a non-default output")
    selection = runner.registered_selection()
    smooth_bundle, rugged_bundle = selected_bundles()
    smooth_rows = [
        smooth_diagnostic(
            runner.SMOOTH_TASK,
            seed_index,
            str(seed),
            n=int(smooth_bundle["n"]),
            samples=args.samples,
            starts=args.starts,
        )
        for seed_index, seed in enumerate(smooth_bundle["seeds"])
    ]
    rugged_items = [
        (
            runner.RUGGED_TASKS[selection["k"]],
            seed_index,
            str(seed),
            int(rugged_bundle["n"]),
            int(rugged_bundle["k"]),
            args.samples,
            args.starts,
        )
        for seed_index, seed in enumerate(rugged_bundle["seeds"])
    ]
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.max_workers) as pool:
        rugged_rows = list(pool.map(rugged_diagnostic, rugged_items, chunksize=1))
    rows = [*smooth_rows, *rugged_rows]
    payload = {
        "schema_version": 5,
        "method": (
            "paired held-out random/neighbor samples, exact Permuted LeadingOnes "
            "topology, and deterministic NK multi-start greedy ascent"
        ),
        "selected_k": selection["k"],
        "selected_budget": selection["budget"],
        "random_samples": args.samples,
        "greedy_starts": args.starts,
        "fully_registered_run": registered,
        "landscapes": rows,
        "difficulty_gates": difficulty_gates(rows, starts=args.starts),
        "interpretation": (
            "These held-out diagnostics establish landscape properties only. "
            "They do not use or establish a topology performance effect."
        ),
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload["difficulty_gates"], indent=2))
    if registered and not payload["difficulty_gates"]["heldout_difficulty_passes"]:
        raise SystemExit("registered v5 held-out difficulty diagnostics failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
