#!/usr/bin/env python3
"""Run the fixed, sequential fresh replication of the extreme K=32 window."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import calibrate_threshold_v3_social as social
from experiments.multi_island_hard import run_threshold_v6_extreme_phase as phase

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "threshold_v6_extreme_window_followup_raw.json"
DEFAULT_CHECKPOINT = Path("/var/tmp/coral-threshold-v6-extreme-window-followup-v1-checkpoint.json")
CHECKPOINT_SCHEMA_VERSION = 1
CHECKPOINT_EVERY = 24
FOLLOWUP_CELLS = ((32, 32768), (32, 65536))
FOLLOWUP_BLOCKS = 192
REFERENCE_SAMPLES = phase.REGISTERED_REFERENCE_SAMPLES
SEED_NAMESPACE = "threshold-v6-extreme-window-followup-heldout"
POLICY_NAMESPACE = "threshold-v6-extreme-window-followup-policy"
INITIAL_SALT = phase.INITIAL_SALT


def followup_seed(block: int) -> str:
    return hashlib.sha256(f"{SEED_NAMESPACE}:{block}".encode()).hexdigest()


def followup_policy_seed(block: int) -> int:
    return int.from_bytes(
        hashlib.sha256(f"{POLICY_NAMESPACE}:{block}".encode()).digest()[:8], "big"
    )


def seed_sha256(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def prior_seed_hashes() -> set[str]:
    hashes = phase.prior_seed_hashes()
    hashes.update(seed_sha256(phase.phase_seed(block)) for block in range(phase.REGISTERED_BLOCKS))
    # The original selected-cell confirmation is a separate held-out namespace.
    old_namespace = "threshold-v6-extreme-confirmation-heldout"
    hashes.update(
        seed_sha256(hashlib.sha256(f"{old_namespace}:{block}".encode()).hexdigest())
        for block in range(192)
    )
    return hashes


def validate_seed_isolation(seeds: tuple[str, ...]) -> None:
    hashes = tuple(seed_sha256(seed) for seed in seeds)
    if len(set(hashes)) != len(hashes):
        raise ValueError("window follow-up seeds are not unique")
    overlap = set(hashes) & prior_seed_hashes()
    if overlap:
        raise ValueError(f"window follow-up seeds overlap prior data: {sorted(overlap)}")


def item_key(item: phase.WorkItem) -> str:
    return ":".join((str(item.difficulty), str(item.budget), str(item.block), item.condition))


def work_items(*, cells: tuple[tuple[int, int], ...], blocks: int) -> list[phase.WorkItem]:
    seeds = tuple(followup_seed(block) for block in range(blocks))
    validate_seed_isolation(seeds)
    return [
        phase.WorkItem(
            "rugged",
            k,
            budget,
            block,
            seeds[block],
            followup_policy_seed(block),
            condition,
        )
        for k, budget in cells
        for block in range(blocks)
        for condition in phase.CONDITIONS
    ]


def configuration(*, cells: tuple[tuple[int, int], ...], blocks: int, reference_samples: int) -> dict[str, Any]:
    return {
        "cells": [[k, budget] for k, budget in cells],
        "rugged_n": phase.RUGGED_N,
        "blocks": blocks,
        "reference_samples": reference_samples,
        "conditions": list(phase.CONDITIONS),
        "mutation_policy": phase.MUTATION_POLICY,
        "initial_salt": INITIAL_SALT,
        "seed_namespace": SEED_NAMESPACE,
        "policy_namespace": POLICY_NAMESPACE,
        "seed_hashes": [seed_sha256(followup_seed(block)) for block in range(blocks)],
        "policy_seed_hashes": [
            hashlib.sha256(str(followup_policy_seed(block)).encode()).hexdigest()
            for block in range(blocks)
        ],
    }


def validate_result(item: phase.WorkItem, result: Any) -> dict[str, float]:
    if not isinstance(result, dict) or set(result) != {"best_score"}:
        raise ValueError(f"invalid window follow-up result: {item_key(item)}")
    score = result["best_score"]
    if not isinstance(score, (int, float)) or not 0 <= float(score) <= 1:
        raise ValueError(f"invalid window follow-up score: {item_key(item)}")
    return {"best_score": float(score)}


def load_checkpoint(path: Path, *, expected_configuration: dict[str, Any], items: list[phase.WorkItem]) -> dict[str, dict[str, float]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise ValueError("unexpected window follow-up checkpoint schema")
    if payload.get("configuration") != expected_configuration:
        raise ValueError("window follow-up checkpoint configuration drifted")
    completed = payload.get("completed")
    expected = {item_key(item): item for item in items}
    if not isinstance(completed, dict) or payload.get("expected_items") != len(items):
        raise ValueError("window follow-up checkpoint matrix is invalid")
    if payload.get("completed_items") != len(completed):
        raise ValueError("window follow-up checkpoint count drifted")
    if payload.get("complete") is not (len(completed) == len(items)):
        raise ValueError("window follow-up checkpoint completion flag drifted")
    if set(completed) - set(expected):
        raise ValueError("window follow-up checkpoint has unexpected items")
    return {key: validate_result(expected[key], value) for key, value in completed.items()}


def write_checkpoint(path: Path, *, run_configuration: dict[str, Any], completed: dict[str, dict[str, float]], expected_items: int) -> None:
    payload = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "configuration": run_configuration,
        "expected_items": expected_items,
        "completed_items": len(completed),
        "complete": len(completed) == expected_items,
        "completed": completed,
        "interpretation_lock": "Only counts may be inspected before complete=true.",
    }
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def run_resumable(*, cells: tuple[tuple[int, int], ...], blocks: int, reference_samples: int, max_workers: int, checkpoint: Path, checkpoint_every: int, fully_registered_run: bool) -> dict[str, Any]:
    if checkpoint_every != CHECKPOINT_EVERY:
        raise ValueError("registered follow-up requires checkpoint cadence 24")
    items = work_items(cells=cells, blocks=blocks)
    run_configuration = configuration(cells=cells, blocks=blocks, reference_samples=reference_samples)
    completed = load_checkpoint(checkpoint, expected_configuration=run_configuration, items=items)
    missing = [item for item in items if item_key(item) not in completed]
    if missing:
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as pool:
            for index, (item, result) in enumerate(pool.map(phase.run_item, missing, chunksize=1), start=1):
                completed[item_key(item)] = validate_result(item, result)
                if index % checkpoint_every == 0 or index == len(missing):
                    write_checkpoint(checkpoint, run_configuration=run_configuration, completed=completed, expected_items=len(items))
                    print(json.dumps({"checkpoint_completed": len(completed), "checkpoint_expected": len(items)}), flush=True)
    if len(completed) != len(items):
        raise RuntimeError("window follow-up ended incomplete")

    seeds = tuple(followup_seed(block) for block in range(blocks))
    grouped: dict[tuple[int, int, int], dict[str, dict[str, float]]] = {}
    for item in items:
        grouped.setdefault((item.difficulty, item.budget, item.block), {})[item.condition] = completed[item_key(item)]
    rows = []
    for (k, budget, block), conditions in sorted(grouped.items()):
        if set(conditions) != set(phase.CONDITIONS):
            raise RuntimeError(f"incomplete topology triplet: {(k, budget, block)}")
        rows.append({
            "k": k,
            "budget": budget,
            "block": block,
            "seed_sha256": seed_sha256(seeds[block]),
            "policy_seed_sha256": hashlib.sha256(str(followup_policy_seed(block)).encode()).hexdigest(),
            "conditions": conditions,
        })
    references = [
        {
            "k": k,
            "budget": budget,
            "block": block,
            "seed_sha256": seed_sha256(seeds[block]),
            **social.random_reference(phase.RUGGED_N, k, seeds[block], samples=reference_samples),
        }
        for k, budget in cells
        for block in range(blocks)
    ]
    return {
        "schema_version": 1,
        "purpose": "fixed sequential fresh replication of the extreme K=32 budget window",
        "fully_registered_run": fully_registered_run,
        "outcome_aware_sequential_followup": True,
        "rugged_n": phase.RUGGED_N,
        "cells": [[k, budget] for k, budget in cells],
        "conditions": list(phase.CONDITIONS),
        "mutation_policy": phase.MUTATION_POLICY,
        "imitation": 1.0,
        "migration": "three move-not-copy elite rotations at B/4, B/2, 3B/4",
        "blocks_per_cell": blocks,
        "reference_samples_per_cell_block": reference_samples,
        "prior_seed_overlap": False,
        "rows": rows,
        "rugged_random_references": references,
        "interpretation_limit": "Sequential follow-up only; not pooled with or a replacement for the original confirmation.",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--checkpoint-every", type=int, default=CHECKPOINT_EVERY)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--allow-reduced", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cells = FOLLOWUP_CELLS if not args.allow_reduced else ((2, 32),)
    blocks = FOLLOWUP_BLOCKS if not args.allow_reduced else 2
    reference_samples = REFERENCE_SAMPLES if not args.allow_reduced else 16
    if not args.allow_reduced and args.output != DEFAULT_OUTPUT:
        raise SystemExit("registered follow-up output path drifted")
    payload = run_resumable(
        cells=cells,
        blocks=blocks,
        reference_samples=reference_samples,
        max_workers=args.max_workers,
        checkpoint=args.checkpoint,
        checkpoint_every=args.checkpoint_every,
        fully_registered_run=not args.allow_reduced,
    )
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"fully_registered_run": payload["fully_registered_run"], "cells": payload["cells"], "blocks_per_cell": payload["blocks_per_cell"], "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
