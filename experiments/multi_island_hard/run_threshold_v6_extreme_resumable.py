#!/usr/bin/env python3
"""Run the registered extreme phase map with validated resumable checkpoints."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import calibrate_threshold_v3_social as social
from experiments.multi_island_hard import run_threshold_v6_extreme_phase as runner

DEFAULT_CHECKPOINT = Path("/var/tmp/coral-threshold-v6-extreme-phase-v3-checkpoint.json")
CHECKPOINT_SCHEMA_VERSION = 1
REGISTERED_CHECKPOINT_EVERY = 24


def configuration(
    *,
    smooth_sizes: tuple[int, ...],
    rugged_ks: tuple[int, ...],
    budgets: tuple[int, ...],
    blocks: int,
    reference_samples: int,
) -> dict[str, Any]:
    return {
        "smooth_sizes": list(smooth_sizes),
        "rugged_n": runner.RUGGED_N,
        "rugged_ks": list(rugged_ks),
        "budgets": list(budgets),
        "blocks": blocks,
        "reference_samples": reference_samples,
        "conditions": list(runner.CONDITIONS),
        "mutation_policy": runner.MUTATION_POLICY,
        "initial_salt": runner.INITIAL_SALT,
        "seed_hashes": [runner.seed_sha256(runner.phase_seed(block)) for block in range(blocks)],
        "policy_seed_hashes": [
            hashlib.sha256(str(runner.phase_policy_seed(block)).encode()).hexdigest()
            for block in range(blocks)
        ],
    }


def work_items(
    *,
    smooth_sizes: tuple[int, ...],
    rugged_ks: tuple[int, ...],
    budgets: tuple[int, ...],
    blocks: int,
) -> list[runner.WorkItem]:
    seeds = tuple(runner.phase_seed(block) for block in range(blocks))
    runner.validate_seed_isolation(seeds)
    return [
        runner.WorkItem(
            family,
            difficulty,
            budget,
            block,
            seeds[block],
            runner.phase_policy_seed(block),
            condition,
        )
        for family, difficulties in (
            ("smooth", smooth_sizes),
            ("rugged", rugged_ks),
        )
        for difficulty in difficulties
        for budget in budgets
        for block in range(blocks)
        for condition in runner.CONDITIONS
    ]


def item_key(item: runner.WorkItem) -> str:
    return ":".join(
        (
            item.family,
            str(item.difficulty),
            str(item.budget),
            str(item.block),
            item.condition,
        )
    )


def validate_result(item: runner.WorkItem, result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError(f"checkpoint result is not an object: {item_key(item)}")
    score = result.get("best_score")
    if not isinstance(score, (int, float)) or not 0 <= float(score) <= 1:
        raise ValueError(f"invalid checkpoint score: {item_key(item)}")
    if item.family == "smooth":
        prefix = result.get("best_prefix")
        if not isinstance(prefix, int) or not 0 <= prefix <= item.difficulty:
            raise ValueError(f"invalid checkpoint Smooth prefix: {item_key(item)}")
        if abs(float(score) - prefix / item.difficulty) > 1e-12:
            raise ValueError(f"checkpoint Smooth score/prefix mismatch: {item_key(item)}")
        if result.get("exact") is not (prefix == item.difficulty):
            raise ValueError(f"invalid checkpoint Smooth exact flag: {item_key(item)}")
    return result


def load_checkpoint(
    path: Path,
    *,
    expected_configuration: dict[str, Any],
    items: list[runner.WorkItem],
) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise ValueError("unexpected extreme checkpoint schema")
    if payload.get("configuration") != expected_configuration:
        raise ValueError("extreme checkpoint configuration drifted")
    expected = {item_key(item): item for item in items}
    completed = payload.get("completed")
    if not isinstance(completed, dict):
        raise ValueError("extreme checkpoint completed map is invalid")
    if payload.get("expected_items") != len(items):
        raise ValueError("extreme checkpoint expected-item count drifted")
    if payload.get("completed_items") != len(completed):
        raise ValueError("extreme checkpoint completed-item count drifted")
    expected_complete = len(completed) == len(items)
    if payload.get("complete") is not expected_complete:
        raise ValueError("extreme checkpoint completion flag drifted")
    extra = set(completed) - set(expected)
    if extra:
        raise ValueError(f"extreme checkpoint has {len(extra)} unexpected items")
    return {key: validate_result(expected[key], result) for key, result in completed.items()}


def write_checkpoint(
    path: Path,
    *,
    run_configuration: dict[str, Any],
    completed: dict[str, dict[str, Any]],
    expected_items: int,
    complete: bool,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "configuration": run_configuration,
        "expected_items": expected_items,
        "completed_items": len(completed),
        "complete": complete,
        "completed": completed,
        "interpretation_lock": (
            "Checkpoint outcomes must not be analyzed before the registered run completes."
        ),
    }
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def assemble_payload(
    *,
    smooth_sizes: tuple[int, ...],
    rugged_ks: tuple[int, ...],
    budgets: tuple[int, ...],
    blocks: int,
    reference_samples: int,
    items: list[runner.WorkItem],
    completed: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    seeds = tuple(runner.phase_seed(block) for block in range(blocks))
    grouped: dict[tuple[str, int, int, int], dict[str, dict[str, Any]]] = {}
    for item in items:
        key = (item.family, item.difficulty, item.budget, item.block)
        grouped.setdefault(key, {})[item.condition] = completed[item_key(item)]
    rows = []
    for (family, difficulty, budget, block), scores in sorted(grouped.items()):
        if set(scores) != set(runner.CONDITIONS):
            raise RuntimeError(
                f"incomplete topology triplet: {(family, difficulty, budget, block)}"
            )
        rows.append(
            {
                "family": family,
                "n": difficulty if family == "smooth" else runner.RUGGED_N,
                "k": 0 if family == "smooth" else difficulty,
                "budget": budget,
                "block": block,
                "seed_sha256": runner.seed_sha256(seeds[block]),
                "policy_seed_sha256": hashlib.sha256(
                    str(runner.phase_policy_seed(block)).encode()
                ).hexdigest(),
                "conditions": scores,
            }
        )
    references = [
        {
            "k": k,
            "block": block,
            "seed_sha256": runner.seed_sha256(seeds[block]),
            **social.random_reference(
                runner.RUGGED_N,
                k,
                seeds[block],
                samples=reference_samples,
            ),
        }
        for k in rugged_ks
        for block in range(blocks)
    ]
    registered = runner.registered_configuration(
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
        "rugged_n": runner.RUGGED_N,
        "rugged_k_values": list(rugged_ks),
        "rugged_affected_fractions": [(k + 1) / runner.RUGGED_N for k in rugged_ks],
        "budgets": list(budgets),
        "conditions": list(runner.CONDITIONS),
        "mutation_policy": runner.MUTATION_POLICY,
        "imitation": 1.0,
        "migration": "three move-not-copy elite rotations at B/4, B/2, 3B/4",
        "blocks": blocks,
        "inference_unit": "paired landscape-policy block",
        "reference_samples_per_rugged_block": reference_samples,
        "prior_seed_overlap": False,
        "rows": rows,
        "rugged_random_references": references,
        "interpretation_limit": (
            "This maps a frozen scripted mechanism beyond the original v6 ruggedness "
            "boundary. It does not establish natural-agent, CORAL-anchor, or real-task "
            "validity."
        ),
    }


def run_resumable(
    *,
    smooth_sizes: tuple[int, ...],
    rugged_ks: tuple[int, ...],
    budgets: tuple[int, ...],
    blocks: int,
    reference_samples: int,
    max_workers: int,
    checkpoint: Path,
    checkpoint_every: int,
) -> dict[str, Any]:
    items = work_items(
        smooth_sizes=smooth_sizes,
        rugged_ks=rugged_ks,
        budgets=budgets,
        blocks=blocks,
    )
    run_configuration = configuration(
        smooth_sizes=smooth_sizes,
        rugged_ks=rugged_ks,
        budgets=budgets,
        blocks=blocks,
        reference_samples=reference_samples,
    )
    completed = load_checkpoint(
        checkpoint,
        expected_configuration=run_configuration,
        items=items,
    )
    missing = [item for item in items if item_key(item) not in completed]
    if missing:
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as pool:
            for index, (item, result) in enumerate(
                pool.map(runner.run_item, missing, chunksize=1),
                start=1,
            ):
                completed[item_key(item)] = validate_result(item, result)
                if index % checkpoint_every == 0 or index == len(missing):
                    write_checkpoint(
                        checkpoint,
                        run_configuration=run_configuration,
                        completed=completed,
                        expected_items=len(items),
                        complete=len(completed) == len(items),
                    )
                    print(
                        json.dumps(
                            {
                                "checkpoint_completed": len(completed),
                                "checkpoint_expected": len(items),
                            }
                        ),
                        flush=True,
                    )
    if len(completed) != len(items):
        raise RuntimeError("resumable extreme phase map ended incomplete")
    return assemble_payload(
        smooth_sizes=smooth_sizes,
        rugged_ks=rugged_ks,
        budgets=budgets,
        blocks=blocks,
        reference_samples=reference_samples,
        items=items,
        completed=completed,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=runner.DEFAULT_OUTPUT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--checkpoint-every", type=int, default=REGISTERED_CHECKPOINT_EVERY)
    parser.add_argument("--smooth-sizes", type=int, nargs="+", default=list(runner.SMOOTH_SIZES))
    parser.add_argument("--rugged-ks", type=int, nargs="+", default=list(runner.RUGGED_K_VALUES))
    parser.add_argument("--budgets", type=int, nargs="+", default=list(runner.BUDGETS))
    parser.add_argument("--blocks", type=int, default=runner.REGISTERED_BLOCKS)
    parser.add_argument(
        "--reference-samples", type=int, default=runner.REGISTERED_REFERENCE_SAMPLES
    )
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--allow-reduced", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    smooth_sizes = tuple(sorted(set(args.smooth_sizes)))
    rugged_ks = tuple(sorted(set(args.rugged_ks)))
    budgets = tuple(sorted(set(args.budgets)))
    registered = runner.registered_configuration(
        smooth_sizes=smooth_sizes,
        rugged_ks=rugged_ks,
        budgets=budgets,
        blocks=args.blocks,
        reference_samples=args.reference_samples,
    )
    invalid = bool(
        not smooth_sizes
        or not rugged_ks
        or not budgets
        or min(smooth_sizes) < 8
        or min(rugged_ks) < 1
        or max(rugged_ks) >= runner.RUGGED_N
        or min(budgets) < len(social.BASE_AGENT_IDS)
        or any(budget % len(social.BASE_AGENT_IDS) for budget in budgets)
        or args.blocks < 2
        or args.reference_samples < 16
        or args.max_workers < 1
        or args.checkpoint_every < 1
    )
    if invalid:
        raise SystemExit("invalid resumable extreme phase-map configuration")
    if not registered and (not args.allow_reduced or args.output == runner.DEFAULT_OUTPUT):
        raise SystemExit("reduced resumable runs require --allow-reduced and a non-default output")
    if registered and args.checkpoint_every != REGISTERED_CHECKPOINT_EVERY:
        raise SystemExit("registered run requires the registered checkpoint cadence")
    payload = run_resumable(
        smooth_sizes=smooth_sizes,
        rugged_ks=rugged_ks,
        budgets=budgets,
        blocks=args.blocks,
        reference_samples=args.reference_samples,
        max_workers=args.max_workers,
        checkpoint=args.checkpoint,
        checkpoint_every=args.checkpoint_every,
    )
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(
        json.dumps(
            {
                "fully_registered_run": payload["fully_registered_run"],
                "topology_triplets": len(payload["rows"]),
                "output": str(args.output),
                "checkpoint": str(args.checkpoint),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
