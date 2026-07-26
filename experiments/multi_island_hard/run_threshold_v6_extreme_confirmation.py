#!/usr/bin/env python3
"""Run the fresh-seed confirmation selected from the extreme phase map."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import calibrate_threshold_v3_social as social
from experiments.multi_island_hard import run_threshold_v6_extreme_phase as discovery_runner
from experiments.multi_island_hard import select_threshold_v6_extreme_confirmation as selector

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "threshold_v6_extreme_confirmation_raw.json"
DEFAULT_CHECKPOINT = Path("/var/tmp/coral-threshold-v6-extreme-confirmation-v1-checkpoint.json")
CHECKPOINT_SCHEMA_VERSION = 1
REGISTERED_CHECKPOINT_EVERY = 24


def confirmation_seed(block: int) -> str:
    return hashlib.sha256(
        f"{selector.CONFIRMATION_SEED_NAMESPACE}:{block}".encode()
    ).hexdigest()


def confirmation_policy_seed(block: int) -> int:
    return int.from_bytes(
        hashlib.sha256(
            f"{selector.CONFIRMATION_POLICY_SEED_NAMESPACE}:{block}".encode()
        ).digest()[:8],
        "big",
    )


def seed_sha256(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def prior_seed_hashes() -> set[str]:
    hashes = discovery_runner.prior_seed_hashes()
    hashes.update(
        discovery_runner.seed_sha256(discovery_runner.phase_seed(block))
        for block in range(discovery_runner.REGISTERED_BLOCKS)
    )
    return hashes


def validate_seed_isolation(seeds: tuple[str, ...]) -> None:
    hashes = tuple(map(seed_sha256, seeds))
    if len(set(hashes)) != len(hashes):
        raise ValueError("confirmation seeds are not unique")
    overlap = set(hashes) & prior_seed_hashes()
    if overlap:
        raise ValueError(f"confirmation seeds overlap prior data: {sorted(overlap)}")


def load_registered_selection(
    selection_path: Path,
    discovery_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    discovery_bytes = discovery_path.read_bytes()
    discovery_sha = hashlib.sha256(discovery_bytes).hexdigest()
    discovery = json.loads(discovery_bytes)
    selection_bytes = selection_path.read_bytes()
    selection = json.loads(selection_bytes)
    selector.validate_selection(
        selection,
        discovery=discovery,
        discovery_sha256=discovery_sha,
    )
    return selection, discovery, hashlib.sha256(selection_bytes).hexdigest(), discovery_sha


def work_items(
    *,
    k: int,
    budget: int,
    blocks: int,
) -> list[discovery_runner.WorkItem]:
    seeds = tuple(confirmation_seed(block) for block in range(blocks))
    validate_seed_isolation(seeds)
    return [
        discovery_runner.WorkItem(
            "rugged",
            k,
            budget,
            block,
            seeds[block],
            confirmation_policy_seed(block),
            condition,
        )
        for block in range(blocks)
        for condition in discovery_runner.CONDITIONS
    ]


def item_key(item: discovery_runner.WorkItem) -> str:
    return f"{item.block}:{item.condition}"


def configuration(
    *,
    k: int,
    budget: int,
    blocks: int,
    reference_samples: int,
    discovery_source_sha256: str,
    selection_file_sha256: str,
) -> dict[str, Any]:
    return {
        "rugged_n": discovery_runner.RUGGED_N,
        "k": k,
        "budget": budget,
        "blocks": blocks,
        "reference_samples": reference_samples,
        "conditions": list(discovery_runner.CONDITIONS),
        "mutation_policy": discovery_runner.MUTATION_POLICY,
        "initial_salt": discovery_runner.INITIAL_SALT,
        "discovery_source_sha256": discovery_source_sha256,
        "selection_file_sha256": selection_file_sha256,
        "seed_hashes": [seed_sha256(confirmation_seed(block)) for block in range(blocks)],
        "policy_seed_hashes": [
            hashlib.sha256(str(confirmation_policy_seed(block)).encode()).hexdigest()
            for block in range(blocks)
        ],
    }


def validate_result(item: discovery_runner.WorkItem, result: Any) -> dict[str, float]:
    if not isinstance(result, dict):
        raise ValueError(f"checkpoint result is not an object: {item_key(item)}")
    score = result.get("best_score")
    if not isinstance(score, (int, float)) or not 0 <= float(score) <= 1:
        raise ValueError(f"invalid checkpoint score: {item_key(item)}")
    if set(result) != {"best_score"}:
        raise ValueError(f"unexpected confirmation result fields: {item_key(item)}")
    return {"best_score": float(score)}


def load_checkpoint(
    path: Path,
    *,
    expected_configuration: dict[str, Any],
    items: list[discovery_runner.WorkItem],
) -> dict[str, dict[str, float]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise ValueError("unexpected confirmation checkpoint schema")
    if payload.get("configuration") != expected_configuration:
        raise ValueError("confirmation checkpoint configuration drifted")
    expected = {item_key(item): item for item in items}
    completed = payload.get("completed")
    if not isinstance(completed, dict):
        raise ValueError("confirmation checkpoint completed map is invalid")
    if payload.get("expected_items") != len(items):
        raise ValueError("confirmation checkpoint expected-item count drifted")
    if payload.get("completed_items") != len(completed):
        raise ValueError("confirmation checkpoint completed-item count drifted")
    if payload.get("complete") is not (len(completed) == len(items)):
        raise ValueError("confirmation checkpoint completion flag drifted")
    if set(completed) - set(expected):
        raise ValueError("confirmation checkpoint has unexpected items")
    return {key: validate_result(expected[key], result) for key, result in completed.items()}


def write_checkpoint(
    path: Path,
    *,
    run_configuration: dict[str, Any],
    completed: dict[str, dict[str, float]],
    expected_items: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "configuration": run_configuration,
        "expected_items": expected_items,
        "completed_items": len(completed),
        "complete": len(completed) == expected_items,
        "completed": completed,
        "interpretation_lock": (
            "Do not inspect confirmation outcomes until completed_items equals expected_items."
        ),
    }
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def run_resumable(
    *,
    k: int,
    budget: int,
    blocks: int,
    reference_samples: int,
    max_workers: int,
    checkpoint: Path,
    checkpoint_every: int,
    discovery_source_sha256: str,
    selection_file_sha256: str,
    fully_registered_run: bool,
) -> dict[str, Any]:
    items = work_items(k=k, budget=budget, blocks=blocks)
    run_configuration = configuration(
        k=k,
        budget=budget,
        blocks=blocks,
        reference_samples=reference_samples,
        discovery_source_sha256=discovery_source_sha256,
        selection_file_sha256=selection_file_sha256,
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
                pool.map(discovery_runner.run_item, missing, chunksize=1),
                start=1,
            ):
                completed[item_key(item)] = validate_result(item, result)
                if index % checkpoint_every == 0 or index == len(missing):
                    write_checkpoint(
                        checkpoint,
                        run_configuration=run_configuration,
                        completed=completed,
                        expected_items=len(items),
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
        raise RuntimeError("confirmation run ended incomplete")

    seeds = tuple(confirmation_seed(block) for block in range(blocks))
    rows = []
    for block in range(blocks):
        conditions = {
            condition: completed[f"{block}:{condition}"]
            for condition in discovery_runner.CONDITIONS
        }
        rows.append(
            {
                "block": block,
                "seed_sha256": seed_sha256(seeds[block]),
                "policy_seed_sha256": hashlib.sha256(
                    str(confirmation_policy_seed(block)).encode()
                ).hexdigest(),
                "conditions": conditions,
            }
        )
    references = [
        {
            "block": block,
            "seed_sha256": seed_sha256(seeds[block]),
            **social.random_reference(
                discovery_runner.RUGGED_N,
                k,
                seeds[block],
                samples=reference_samples,
            ),
        }
        for block in range(blocks)
    ]
    return {
        "schema_version": 1,
        "purpose": "fresh-seed confirmation of one blindly selected extreme Rugged cell",
        "fully_registered_run": fully_registered_run,
        "discovery_source_sha256": discovery_source_sha256,
        "selection_file_sha256": selection_file_sha256,
        "rugged_n": discovery_runner.RUGGED_N,
        "k": k,
        "affected_fraction": (k + 1) / discovery_runner.RUGGED_N,
        "budget": budget,
        "blocks": blocks,
        "reference_samples_per_block": reference_samples,
        "conditions": list(discovery_runner.CONDITIONS),
        "mutation_policy": discovery_runner.MUTATION_POLICY,
        "imitation": 1.0,
        "migration": "three move-not-copy elite rotations at B/4, B/2, 3B/4",
        "prior_seed_overlap": False,
        "rows": rows,
        "rugged_random_references": references,
        "interpretation_limit": (
            "A pass confirms only the frozen scripted mechanism at the selected cell. "
            "Natural-agent, CORAL-anchor, and real-task gates remain separate."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=selector.DEFAULT_OUTPUT)
    parser.add_argument("--discovery", type=Path, default=selector.DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--checkpoint-every", type=int, default=REGISTERED_CHECKPOINT_EVERY)
    parser.add_argument("--max-workers", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.checkpoint_every != REGISTERED_CHECKPOINT_EVERY:
        raise SystemExit("registered confirmation requires the registered checkpoint cadence")
    if args.max_workers < 1:
        raise SystemExit("confirmation max-workers must be positive")
    selection, _, selection_sha, discovery_sha = load_registered_selection(
        args.selection,
        args.discovery,
    )
    selected = selection["selected_cell"]
    payload = run_resumable(
        k=int(selected["k"]),
        budget=int(selected["budget"]),
        blocks=selector.CONFIRMATION_BLOCKS,
        reference_samples=selector.CONFIRMATION_REFERENCE_SAMPLES,
        max_workers=args.max_workers,
        checkpoint=args.checkpoint,
        checkpoint_every=args.checkpoint_every,
        discovery_source_sha256=discovery_sha,
        selection_file_sha256=selection_sha,
        fully_registered_run=True,
    )
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(
        json.dumps(
            {
                "fully_registered_run": True,
                "selected_cell": {"k": payload["k"], "budget": payload["budget"]},
                "blocks": payload["blocks"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
