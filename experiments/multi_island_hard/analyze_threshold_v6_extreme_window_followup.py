#!/usr/bin/env python3
"""Audit and analyze the fixed sequential extreme-window replication."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import analyze_threshold_v6_extreme_phase as phase_analyzer
from experiments.multi_island_hard import analyze_threshold_v6_phase_map as base
from experiments.multi_island_hard import run_threshold_v6_extreme_window_followup as runner

ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = runner.DEFAULT_OUTPUT
DEFAULT_OUTPUT = ROOT / "threshold_v6_extreme_window_followup_analysis.json"
ONE_SIDED_ALPHA = 0.05
GLOBAL_FLOOR = 0.25
PARTITION_FLOOR = 0.10


def audit(payload: dict[str, Any], *, require_registered: bool) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("unexpected follow-up schema version")
    if require_registered and payload.get("fully_registered_run") is not True:
        errors.append("follow-up is not the fully registered run")
    if payload.get("outcome_aware_sequential_followup") is not True:
        errors.append("follow-up outcome-aware status is not explicit")
    if int(payload.get("rugged_n", -1)) != runner.phase.RUGGED_N:
        errors.append("follow-up Rugged dimension drifted")
    if payload.get("conditions") != list(runner.phase.CONDITIONS):
        errors.append("follow-up topology conditions drifted")
    if payload.get("mutation_policy") != runner.phase.MUTATION_POLICY:
        errors.append("follow-up mutation policy drifted")
    if payload.get("prior_seed_overlap") is not False:
        errors.append("follow-up seed isolation is not attested")

    cells = tuple(tuple(map(int, cell)) for cell in payload.get("cells", []))
    if require_registered and cells != runner.FOLLOWUP_CELLS:
        errors.append("follow-up cell grid drifted")
    blocks = int(payload.get("blocks_per_cell", 0))
    references = {(int(row.get("k")), int(row.get("budget")), int(row.get("block"))): row for row in payload.get("rugged_random_references", [])}
    expected_references = {(k, budget, block) for k, budget in cells for block in range(blocks)}
    if set(references) != expected_references:
        errors.append("follow-up random-reference matrix is incomplete")

    seeds = tuple(runner.followup_seed(block) for block in range(blocks))
    runner.validate_seed_isolation(seeds)
    expected_seed = {block: runner.seed_sha256(seeds[block]) for block in range(blocks)}
    expected_policy = {
        block: hashlib.sha256(str(runner.followup_policy_seed(block)).encode()).hexdigest()
        for block in range(blocks)
    }
    expected_rows = {(k, budget, block) for k, budget in cells for block in range(blocks)}
    observed: set[tuple[int, int, int]] = set()
    for row in payload.get("rows", []):
        key = (int(row.get("k", -1)), int(row.get("budget", -1)), int(row.get("block", -1)))
        if key in observed:
            errors.append(f"duplicate follow-up row: {key}")
        observed.add(key)
        block = key[2]
        if row.get("seed_sha256") != expected_seed.get(block):
            errors.append(f"follow-up seed drift in {key}")
        if row.get("policy_seed_sha256") != expected_policy.get(block):
            errors.append(f"follow-up policy seed drift in {key}")
        conditions = row.get("conditions", {})
        if set(conditions) != set(runner.phase.CONDITIONS):
            errors.append(f"incomplete follow-up topology triplet: {key}")
            continue
        for condition, result in conditions.items():
            score = result.get("best_score")
            if not isinstance(score, (int, float)) or not 0 <= float(score) <= 1:
                errors.append(f"invalid follow-up score: {key}/{condition}")
    if observed != expected_rows:
        errors.append("follow-up row matrix is incomplete")
    for key, row in references.items():
        if row.get("seed_sha256") != expected_seed.get(key[2]):
            errors.append(f"follow-up reference seed drift in {key}")
        if not isinstance(row.get("random_sd"), (int, float)) or float(row["random_sd"]) <= 0:
            errors.append(f"invalid follow-up random SD in {key}")
    return errors


def interval(values: list[float], *, label: str, lower_probability: float, repetitions: int) -> tuple[float, float]:
    return base.bootstrap_mean_interval(values, label=label, lower_probability=lower_probability, repetitions=repetitions)


def analyze(payload: dict[str, Any], *, require_registered: bool, bootstrap_repetitions: int = base.BOOTSTRAP_REPETITIONS) -> dict[str, Any]:
    errors = audit(payload, require_registered=require_registered)
    if errors:
        raise ValueError("; ".join(errors))
    cells = tuple(tuple(map(int, cell)) for cell in payload["cells"])
    rows = {(int(row["k"]), int(row["budget"]), int(row["block"])): row for row in payload["rows"]}
    references = {(int(row["k"]), int(row["budget"]), int(row["block"])): row for row in payload["rugged_random_references"]}
    blocks = int(payload["blocks_per_cell"])
    cell_results: list[dict[str, Any]] = []
    for k, budget in cells:
        performance: dict[str, Any] = {}
        for condition in runner.phase.CONDITIONS:
            scores = [float(rows[(k, budget, block)]["conditions"][condition]["best_score"]) for block in range(blocks)]
            gains = [(scores[block] - float(references[(k, budget, block)]["random_mean"])) / float(references[(k, budget, block)]["random_sd"]) for block in range(blocks)]
            performance[condition] = {
                "mean_final_best_score": statistics.fmean(scores),
                "mean_gain_over_random_z": statistics.fmean(gains),
            }

        contrasts: dict[str, Any] = {}
        effect_gates: list[bool] = []
        for control, floor in (("global_8", GLOBAL_FLOOR), ("partition_4", PARTITION_FLOOR)):
            standardized = [
                (
                    float(rows[(k, budget, block)]["conditions"]["multi_island_4"]["best_score"])
                    - float(rows[(k, budget, block)]["conditions"][control]["best_score"])
                )
                / float(references[(k, budget, block)]["random_sd"])
                for block in range(blocks)
            ]
            name = control.removesuffix("_8").removesuffix("_4")
            descriptive = interval(standardized, label=f"window-followup:{k}:{budget}:multi-minus-{name}:desc", lower_probability=0.025, repetitions=bootstrap_repetitions)
            lower, _ = interval(standardized, label=f"window-followup:{k}:{budget}:multi-minus-{name}:one-sided", lower_probability=ONE_SIDED_ALPHA, repetitions=bootstrap_repetitions)
            mean = statistics.fmean(standardized)
            passes = bool(mean >= floor and lower > 0)
            effect_gates.append(passes)
            contrasts[f"multi_minus_{name}"] = {
                "mean_random_z_difference": mean,
                "descriptive_random_z_ci": list(descriptive),
                "one_sided_95pct_random_z_lower": lower,
                "practical_floor_random_z": floor,
                "passes": passes,
            }

        progress_floor = phase_analyzer.iid_random_max_floor_z(budget)
        minimum_progress = min(float(result["mean_gain_over_random_z"]) for result in performance.values())
        progress_passes = minimum_progress >= progress_floor
        cell_results.append({
            "k": k,
            "budget": budget,
            "performance": performance,
            "contrasts": contrasts,
            "search_progress_gate": {
                "minimum_topology_gain_over_random_z": minimum_progress,
                "iid_random_search_expected_max_plus_margin_z": progress_floor,
                "passes": progress_passes,
            },
            "followup_point_and_bound_gates_pass": bool(all(effect_gates) and progress_passes),
        })
    return {
        "schema_version": 1,
        "source_fully_registered": bool(payload["fully_registered_run"]),
        "audit_passes": True,
        "outcome_aware_sequential_followup": True,
        "bootstrap_repetitions": bootstrap_repetitions,
        "cells": cell_results,
        "claim_boundary": "Sequential outcome-aware replication only; not pooled with or a replacement for the original confirmation.",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-reduced", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.loads(args.input.read_text())
    result = analyze(payload, require_registered=not args.allow_reduced, bootstrap_repetitions=base.BOOTSTRAP_REPETITIONS)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
