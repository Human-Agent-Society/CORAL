#!/usr/bin/env python3
"""Audit and analyze the registered v6 extreme-hardness extension."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import NormalDist
from typing import Any

from experiments.multi_island_hard import analyze_threshold_v6_phase_map as base
from experiments.multi_island_hard import run_threshold_v6_extreme_phase as runner

ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = runner.DEFAULT_OUTPUT
DEFAULT_OUTPUT = ROOT / "threshold_v6_extreme_phase_analysis.json"
RANDOM_SEARCH_MARGIN_Z = 0.25


def iid_random_max_floor_z(budget: int) -> float:
    """Blom expected-normal-maximum approximation plus a practical margin."""

    if budget < 2:
        raise ValueError("random-search maximum requires at least two draws")
    probability = (budget - 0.375) / (budget + 0.25)
    return NormalDist().inv_cdf(probability) + RANDOM_SEARCH_MARGIN_Z


def expected_keys(payload: dict[str, Any]) -> set[tuple[str, int, int, int]]:
    blocks = range(int(payload["blocks"]))
    budgets = tuple(map(int, payload["budgets"]))
    return {
        ("smooth", n, budget, block)
        for n in map(int, payload["smooth_sizes"])
        for budget in budgets
        for block in blocks
    } | {
        ("rugged", k, budget, block)
        for k in map(int, payload["rugged_k_values"])
        for budget in budgets
        for block in blocks
    }


def audit(payload: dict[str, Any], *, require_registered: bool) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("unexpected schema version")
    if require_registered and not payload.get("fully_registered_run"):
        errors.append("extreme phase map is not the fully registered run")
    try:
        registered = runner.registered_configuration(
            smooth_sizes=tuple(map(int, payload["smooth_sizes"])),
            rugged_ks=tuple(map(int, payload["rugged_k_values"])),
            budgets=tuple(map(int, payload["budgets"])),
            blocks=int(payload["blocks"]),
            reference_samples=int(payload["reference_samples_per_rugged_block"]),
        )
    except (KeyError, TypeError, ValueError):
        registered = False
    if require_registered and not registered:
        errors.append("registered extreme phase-map grid or replication count drifted")
    if int(payload.get("rugged_n", -1)) != runner.RUGGED_N:
        errors.append("Rugged dimension drifted")
    if payload.get("conditions") != list(runner.CONDITIONS):
        errors.append("topology conditions drifted")
    if payload.get("mutation_policy") != runner.MUTATION_POLICY:
        errors.append("mutation policy drifted")
    if payload.get("prior_seed_overlap") is not False:
        errors.append("prior seed isolation is not attested")

    blocks = int(payload.get("blocks", 0))
    expected_seed = {block: runner.seed_sha256(runner.phase_seed(block)) for block in range(blocks)}
    expected_policy = {
        block: hashlib.sha256(str(runner.phase_policy_seed(block)).encode()).hexdigest()
        for block in range(blocks)
    }
    expected = expected_keys(payload)
    observed: set[tuple[str, int, int, int]] = set()
    seed_by_block: dict[int, str] = {}
    for row in payload.get("rows", []):
        family = str(row.get("family"))
        difficulty = int(row.get("n") if family == "smooth" else row.get("k"))
        block = int(row.get("block"))
        key = (family, difficulty, int(row.get("budget")), block)
        if key in observed:
            errors.append(f"duplicate topology triplet: {key}")
        observed.add(key)
        seed_hash = str(row.get("seed_sha256"))
        if seed_hash != expected_seed.get(block):
            errors.append(f"unexpected held-out seed hash in block {block}")
        if row.get("policy_seed_sha256") != expected_policy.get(block):
            errors.append(f"unexpected policy seed hash in block {block}")
        if block in seed_by_block and seed_by_block[block] != seed_hash:
            errors.append(f"seed drift within block {block}")
        seed_by_block[block] = seed_hash
        conditions = row.get("conditions", {})
        if set(conditions) != set(runner.CONDITIONS):
            errors.append(f"incomplete topology triplet: {key}")
            continue
        for condition, result in conditions.items():
            score = result.get("best_score")
            if not isinstance(score, (int, float)) or not 0 <= float(score) <= 1:
                errors.append(f"invalid score at {key}/{condition}")
            if family == "smooth":
                prefix = result.get("best_prefix")
                exact = result.get("exact")
                if not isinstance(prefix, int) or not 0 <= prefix <= difficulty:
                    errors.append(f"invalid Smooth prefix at {key}/{condition}")
                elif abs(float(score) - prefix / difficulty) > 1e-12:
                    errors.append(f"Smooth score/prefix mismatch at {key}/{condition}")
                if isinstance(prefix, int) and exact is not (prefix == difficulty):
                    errors.append(f"Smooth exact flag mismatch at {key}/{condition}")
    if expected - observed:
        errors.append(f"missing {len(expected - observed)} topology triplets")
    if observed - expected:
        errors.append(f"found {len(observed - expected)} unexpected topology triplets")

    expected_references = {
        (k, block) for k in map(int, payload.get("rugged_k_values", [])) for block in range(blocks)
    }
    references: set[tuple[int, int]] = set()
    for row in payload.get("rugged_random_references", []):
        key = (int(row.get("k")), int(row.get("block")))
        if key in references:
            errors.append(f"duplicate Rugged random reference: {key}")
        references.add(key)
        sd = row.get("random_sd")
        if not isinstance(sd, (int, float)) or float(sd) <= 0:
            errors.append(f"invalid Rugged random SD: {key}")
        if row.get("seed_sha256") != expected_seed.get(key[1]):
            errors.append(f"reference seed drift: {key}")
    if references != expected_references:
        errors.append("Rugged random-reference matrix is incomplete")
    return errors


def add_progress_gate(
    rows: list[dict[str, Any]],
    decision: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    passing: list[dict[str, int]] = []
    for row in rows:
        gains = {
            condition: float(metrics["mean_gain_over_random_z"])
            for condition, metrics in row["performance"].items()
        }
        row["effect_gate_passes"] = bool(row["passes"])
        progress_floor = iid_random_max_floor_z(int(row["budget"]))
        row["minimum_topology_gain_over_random_z"] = min(gains.values())
        row["iid_random_search_expected_max_plus_margin_z"] = progress_floor
        row["search_progress_gate"] = bool(
            row["minimum_topology_gain_over_random_z"] >= progress_floor
        )
        row["passes"] = bool(row["effect_gate_passes"] and row["search_progress_gate"])
        if row["passes"]:
            passing.append({"k": int(row["k"]), "budget": int(row["budget"])})
    budgets = tuple(sorted({int(row["budget"]) for row in rows}))
    ks = tuple(sorted({int(row["k"]) for row in rows}))
    decision = dict(decision)
    decision.update(
        {
            "random_search_margin_z": RANDOM_SEARCH_MARGIN_Z,
            "random_search_floor": "Blom expected iid-normal maximum plus margin",
            "passing_cells": passing,
            "earliest_passing_budget_by_k": {
                str(k): next(
                    (budget for budget in budgets if {"k": k, "budget": budget} in passing),
                    None,
                )
                for k in ks
            },
            "phase_region_observed": bool(passing and len(passing) < len(rows)),
        }
    )
    return rows, decision


def analyze(payload: dict[str, Any], *, require_registered: bool) -> dict[str, Any]:
    errors = audit(payload, require_registered=require_registered)
    if errors:
        raise ValueError("; ".join(errors))
    rugged_rows, rugged_decision = base.summarize_rugged(payload)
    rugged_rows, rugged_decision = add_progress_gate(rugged_rows, rugged_decision)
    smooth_rows, smooth_decision = base.summarize_smooth(payload)
    return {
        "schema_version": 1,
        "source_fully_registered": bool(payload["fully_registered_run"]),
        "audit_passes": True,
        "bootstrap_repetitions": base.BOOTSTRAP_REPETITIONS,
        "rugged_phase_map": rugged_rows,
        "rugged_decision": rugged_decision,
        "smooth_phase_map": smooth_rows,
        "smooth_decision": smooth_decision,
        "claim_boundary": (
            "A passing extreme-Rugged phase region is evidence only for the frozen scripted "
            "mechanism. Natural-agent, CORAL-anchor, and real-task gates remain separate."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-reduced", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.allow_reduced and args.output == DEFAULT_OUTPUT:
        raise SystemExit("reduced analyses require a non-default output")
    payload = json.loads(args.input.read_text())
    try:
        result = analyze(payload, require_registered=not args.allow_reduced)
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"extreme phase-map audit failed: {exc}") from exc
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {"rugged": result["rugged_decision"], "smooth": result["smooth_decision"]}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
