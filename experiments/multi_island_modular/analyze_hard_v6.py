#!/usr/bin/env python3
"""Audit v6 with observed assembly reward and origin-aware transfer metrics."""

from __future__ import annotations

import importlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
V6_GRADER_SRC = ROOT / "tasks/hard_active_modular_landscape_v6/grader/src"
sys.path.insert(0, str(V6_GRADER_SRC))
from hard_active_modular_landscape_v6_grader.grader import (  # noqa: E402
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
base.TASKDATA = ROOT / "tasks/hard_active_modular_landscape_v6/taskdata/hard_v6_seed_bundle.json"
base.SEED_BUNDLE_FILENAME = "hard_v6_seed_bundle.json"
base.SEED_SCHEMA_VERSION = 4
base.ROLE_PROTOCOL_FILENAME = "hard_v6_eval_protocol.md"
base.MIN_MODULE_COVERAGE = 16
base.MIN_ISLAND_COVERAGE = 8
base.MIN_EXACT_SIGNAL = 1
base.MIGRATION_DIVISOR = 4
base.MIGRATION_MIN = 128
base.MIGRATION_MAX = 512
base.REMIGRATION_COOLDOWN = 128
base.ANALYZER_LABEL = "Hard v6"
base.__doc__ = __doc__
base.PRIMARY_METRIC = "observed exact-module assembly reward"
base.CONDITIONS = ("global_8", "partition", "multi_island")
base.TOPOLOGY_AGENT_COUNTS = {
    "global_8": "8",
    "partition": "8",
    "multi_island": "8",
}

HEARTBEAT_OVERRIDE = (
    '[{"name":"reflect","every":16},'
    '{"name":"consolidate","every":32,"is_global":true},'
    '{"name":"pivot","every":16,"trigger":"plateau"},'
    '{"name":"lint_wiki","every":32,"is_global":true}]'
)
base.TASKS = ("smooth_hard_v6", "rugged_hard_v6")
base.REPETITIONS = 8
base.BLOCKS = BLOCKS
base.WIDTH = WIDTH
base.CODEBOOK_SIZE = CODEBOOK_SIZE
base.TOTAL_WIDTH = TOTAL_WIDTH
base.active_score = active_score
base.rugged_target = rugged_target
base.target_bits = target_bits


def _eval_payload(record: dict[str, Any]) -> dict[str, Any] | None:
    """Decode the grader's JSON before its appended trace-log hint."""
    text = str(record.get("feedback") or "")
    marker = "eval:"
    start = text.find(marker)
    if start < 0:
        return None
    decoder = json.JSONDecoder()
    try:
        payload, _ = decoder.raw_decode(text[start + len(marker) :].lstrip())
    except (json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _record_is_exact(record: dict[str, Any]) -> bool:
    """Use v6's active tested flag, not its combined top-level score."""
    payload = _eval_payload(record)
    if payload is None:
        return record.get("score") == 1.0
    return payload.get("tested") is True and payload.get("active_score") == 1.0


def _observed_transfer(run_dir: Path, task: str, repetition: int) -> dict[str, Any]:
    """Measure exact modules carried from their discovery island to another."""
    seed = str(base.bundle()["seeds"][repetition - 1])
    mode = base.mode_for(task)
    target_list = [
        target_bits(seed, block, WIDTH) if mode == "smooth" else rugged_target(seed, block, WIDTH)
        for block in range(BLOCKS)
    ]
    known: dict[int, str] = {}
    known_origin: dict[int, str] = {}
    transferred: set[int] = set()
    transfer_events = 0
    origin_coverage: defaultdict[str, set[int]] = defaultdict(set)
    records = base.real_records(run_dir)
    for record in records:
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
        for block in range(BLOCKS):
            bits = candidate[block * WIDTH : (block + 1) * WIDTH]
            prior_origin = known_origin.get(block)
            if (
                prior_origin is not None
                and prior_origin != current
                and known.get(block) == bits
            ):
                transferred.add(block)
                carried_here = True
        # Only an active exact response creates a provenance-backed discovery.
        # Exact inactive bits cannot enter the transfer ledger just because
        # the operator can reconstruct the hidden target offline.
        if _record_is_exact(record):
            bits = candidate[active * WIDTH : (active + 1) * WIDTH]
            if bits == target_list[active] and active not in known:
                known[active] = bits
                known_origin[active] = origin
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


def collect(run_dir: Path, identity: dict[str, Any], task: str, budget: int) -> dict[str, Any]:
    row = base._ORIGINAL_COLLECT(run_dir, identity, task, budget)
    records = base.real_records(run_dir)
    observations = [_eval_payload(record) for record in records]
    valid = [item for item in observations if item is not None]
    exact_counts = [
        int(item["artifact_exact_count"])
        for item in valid
        if isinstance(item.get("artifact_exact_count"), int)
    ]
    artifact_scores = [
        float(item["artifact_score"])
        for item in valid
        if isinstance(item.get("artifact_score"), (int, float))
    ]
    row.update(
        {
            "observed_feedback_count": len(valid),
            "observed_artifact_exact_max": max(exact_counts, default=0),
            "observed_artifact_score_max": max(artifact_scores, default=0.0),
            "observed_artifact_exact_final": exact_counts[-1] if exact_counts else 0,
            **_observed_transfer(run_dir, task, int(identity["repetition"])),
        }
    )
    return row


def integrity(run_dir: Path, identity: dict[str, Any], task: str, budget: int) -> list[str]:
    errors = base._ORIGINAL_INTEGRITY(run_dir, identity, task, budget)
    overrides = base.overrides(identity)
    if overrides.get("agents.heartbeat") != HEARTBEAT_OVERRIDE:
        errors.append("wrong fixed-budget heartbeat cadence")
    records = base.real_records(run_dir)
    payloads = [_eval_payload(record) for record in records]
    if len([item for item in payloads if item is not None]) != len(records):
        errors.append("missing or malformed v6 assembly feedback")
    for item in payloads:
        if item is None:
            continue
        if not isinstance(item.get("artifact_exact_count"), int):
            errors.append("assembly feedback lacks exact-module count")
            break
        if not 0 <= item["artifact_exact_count"] <= BLOCKS:
            errors.append("assembly exact-module count outside v6 bounds")
            break
    return errors


# Keep the audited v4 implementation for parser/provenance logic, while
# retaining the original callables so the wrappers above can delegate cleanly.
base._ORIGINAL_COLLECT = base.collect
base._ORIGINAL_INTEGRITY = base.integrity
base.record_is_exact = _record_is_exact
base.collect = collect
base.integrity = integrity


if __name__ == "__main__":
    raise SystemExit(base.main())
