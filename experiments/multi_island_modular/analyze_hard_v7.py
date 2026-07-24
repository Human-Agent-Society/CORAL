#!/usr/bin/env python3
"""Audit the v7 oracle-free high-difficulty threshold matrix."""

from __future__ import annotations

import importlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
V7_GRADER_SRC = ROOT / "tasks/hard_active_modular_landscape_v7/grader/src"
sys.path.insert(0, str(V7_GRADER_SRC))
from hard_active_modular_landscape_v7_grader.grader import (  # noqa: E402
    BLOCKS,
    CODEBOOK_SIZE,
    TOTAL_WIDTH,
    WIDTH,
    active_score,
    rugged_target,
    target_bits,
)

from experiments.multi_island_modular import analyze_hard_v4 as base  # noqa: E402

base = importlib.reload(base)

base.ROOT = ROOT
base.TASKDATA = ROOT / "tasks/hard_active_modular_landscape_v7/taskdata/hard_v7_seed_bundle.json"
base.SEED_BUNDLE_FILENAME = "hard_v7_seed_bundle.json"
base.SEED_SCHEMA_VERSION = 5
base.ROLE_PROTOCOL_FILENAME = "hard_v7_eval_protocol.md"
base.MIN_MODULE_COVERAGE = 16
base.MIN_ISLAND_COVERAGE = 8
base.MIN_EXACT_SIGNAL = 1
base.MAX_MALFORMED_ATTEMPTS = 1
base.MIGRATION_DIVISOR = 4
base.MIGRATION_MIN = 256
base.MIGRATION_MAX = 2048
base.REMIGRATION_COOLDOWN = 256
base.ANALYZER_LABEL = "Hard v7"
base.__doc__ = __doc__
base.PRIMARY_METRIC = "offline provenance-backed assembly"
base.CONDITIONS = ("global_8", "partition", "multi_island")
base.TOPOLOGY_AGENT_COUNTS = {name: "8" for name in base.CONDITIONS}
base.TASKS = ("smooth_hard_v7", "rugged_hard_v7")
base.REPETITIONS = 8
base.DEFAULT_BUDGETS = (
    1024,
    2048,
    3072,
    4096,
    6144,
    8192,
    16384,
    32768,
    65536,
    98304,
    131072,
    196608,
)
base.BLOCKS = BLOCKS
base.WIDTH = WIDTH
base.CODEBOOK_SIZE = CODEBOOK_SIZE
base.TOTAL_WIDTH = TOTAL_WIDTH
base.active_score = active_score
base.rugged_target = rugged_target
base.target_bits = target_bits
base.record_is_exact = lambda record: record.get("score") == 1.0

HEARTBEAT_OVERRIDE = (
    '[{"name":"reflect","every":16},'
    '{"name":"consolidate","every":32,"is_global":true},'
    '{"name":"pivot","every":16,"trigger":"plateau"},'
    '{"name":"lint_wiki","every":32,"is_global":true}]'
)


def _observed_transfer(run_dir: Path, task: str, repetition: int) -> dict[str, Any]:
    """Count exact modules carried from a discovery island to another island."""
    seed = str(base.bundle()["seeds"][repetition - 1])
    mode = base.mode_for(task)
    target_list = [
        target_bits(seed, block, WIDTH) if mode == "smooth" else rugged_target(seed, block, WIDTH)
        for block in range(BLOCKS)
    ]
    known: dict[int, str] = {}
    known_origins: defaultdict[int, set[str]] = defaultdict(set)
    transferred: set[int] = set()
    observed_destinations: set[tuple[int, str]] = set()
    transfer_events = 0
    origin_coverage: defaultdict[str, set[int]] = defaultdict(set)
    for record in base.real_records(run_dir):
        try:
            candidate, active = base.parse_artifact(
                base.source_at(run_dir, str(record["commit_hash"]))
            )
        except (OSError, ValueError, SyntaxError, KeyError, TypeError):
            continue
        metadata = record.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        current = base.record_island(record)
        origin = str(metadata.get("origin_island_id") or current)
        origin_coverage[origin].add(active)
        carried_here = False
        active_exact = record.get("score") == 1.0
        for block in range(BLOCKS):
            bits = candidate[block * WIDTH : (block + 1) * WIDTH]
            if (
                known_origins.get(block)
                and current not in known_origins[block]
                and known.get(block) == bits
                and not (active_exact and block == active)
                and (block, current) not in observed_destinations
            ):
                transferred.add(block)
                observed_destinations.add((block, current))
                carried_here = True
        if active_exact:
            bits = candidate[active * WIDTH : (active + 1) * WIDTH]
            if bits == target_list[active]:
                known.setdefault(active, bits)
                known_origins[active].add(origin)
        if carried_here:
            transfer_events += 1
    return {
        "transfer_events": transfer_events,
        "transferred_blocks": len(transferred),
        "origin_island_coverage": json.dumps(
            {key: len(value) for key, value in sorted(origin_coverage.items())},
            sort_keys=True,
        ),
    }


def _agent_balance(run_dir: Path, budget: int) -> dict[str, Any]:
    counts: defaultdict[str, int] = defaultdict(int)
    for record in base.real_records(run_dir):
        agent = str(record.get("agent_id") or "unknown")
        counts[agent] += 1
    values = list(counts.values())
    expected = budget / 8
    minimum = min(values, default=0)
    maximum = max(values, default=0)
    return {
        "agent_attempt_counts": json.dumps(dict(sorted(counts.items())), sort_keys=True),
        "agent_attempt_min": minimum,
        "agent_attempt_max": maximum,
        "agent_balance_ratio": (minimum / maximum if maximum else 0.0),
        "agent_quota_gate": len(counts) == 8 and all(value == expected for value in values),
    }


def collect(run_dir: Path, identity: dict[str, Any], task: str, budget: int) -> dict[str, Any]:
    row = _BASE_COLLECT(run_dir, identity, task, budget)
    transfer = _observed_transfer(run_dir, task, int(identity["repetition"]))
    if str(identity["condition"]) != "multi_island":
        transfer["transfer_events"] = 0
        transfer["transferred_blocks"] = 0
    row.update(transfer)
    row.update(_agent_balance(run_dir, budget))
    return row


def integrity(run_dir: Path, identity: dict[str, Any], task: str, budget: int) -> list[str]:
    errors = _BASE_INTEGRITY(run_dir, identity, task, budget)
    values = base.overrides(identity)
    if values.get("agents.heartbeat") != HEARTBEAT_OVERRIDE:
        errors.append("wrong fixed-budget heartbeat cadence")
    if budget % 8 or values.get("run.stop.max_real_attempts_per_agent") != str(budget // 8):
        errors.append("wrong fixed eight-agent evaluation quota")
    if task not in base.TASKS:
        errors.append("unknown v7 task")
    records = base.real_records(run_dir)
    for record in records:
        feedback = str(record.get("feedback") or "")
        if '"invalid_candidate"' in feedback and record.get("score") != 0.0:
            errors.append("invalid v7 candidate did not receive numeric zero score")
            break
    balance = _agent_balance(run_dir, budget)
    if len(records) == budget and not balance["agent_quota_gate"]:
        errors.append(
            "per-agent attempt quota failed: "
            f"min={balance['agent_attempt_min']}, max={balance['agent_attempt_max']}"
        )
    return errors


_BASE_INTEGRITY = base.integrity
_BASE_COLLECT = base.collect
base.integrity = integrity
base.collect = collect


def main() -> int:
    # Import and execute the audited v4 CLI after all package constants are set.
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
