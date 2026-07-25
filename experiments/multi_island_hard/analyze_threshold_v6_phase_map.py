#!/usr/bin/env python3
"""Audit and analyze the preregistered v6 hardness-response phase map."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import run_threshold_v6_phase_map as runner

ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = runner.DEFAULT_OUTPUT
DEFAULT_OUTPUT = ROOT / "threshold_v6_phase_map_analysis.json"
FAMILYWISE_ALPHA = 0.05
BOOTSTRAP_REPETITIONS = 100_000
MULTI_GLOBAL_FLOOR_Z = 0.25
MULTI_PARTITION_FLOOR_Z = 0.10


def percentile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values or not 0 <= probability <= 1:
        raise ValueError("invalid percentile request")
    index = min(len(sorted_values) - 1, max(0, int(probability * len(sorted_values))))
    return sorted_values[index]


def bootstrap_mean_interval(
    values: list[float],
    *,
    label: str,
    lower_probability: float,
    upper_probability: float = 0.975,
    repetitions: int = BOOTSTRAP_REPETITIONS,
) -> tuple[float, float]:
    if len(values) < 2:
        raise ValueError("paired bootstrap requires at least two blocks")
    if not 0 < lower_probability < upper_probability < 1:
        raise ValueError("invalid bootstrap probabilities")
    rng = random.Random(int.from_bytes(hashlib.sha256(label.encode()).digest()[:8], "big"))
    draws = sorted(
        statistics.fmean(rng.choice(values) for _ in values) for _ in range(repetitions)
    )
    return percentile(draws, lower_probability), percentile(draws, upper_probability)


def expected_keys(payload: dict[str, Any]) -> set[tuple[str, int, int, int]]:
    blocks = range(int(payload["blocks"]))
    budgets = tuple(int(value) for value in payload["budgets"])
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
        errors.append("phase map is not the fully registered run")
    try:
        configuration_is_registered = runner.registered_configuration(
            smooth_sizes=tuple(map(int, payload["smooth_sizes"])),
            rugged_ks=tuple(map(int, payload["rugged_k_values"])),
            budgets=tuple(map(int, payload["budgets"])),
            blocks=int(payload["blocks"]),
            reference_samples=int(payload["reference_samples_per_rugged_block"]),
        )
    except (KeyError, TypeError, ValueError):
        configuration_is_registered = False
    if require_registered and not configuration_is_registered:
        errors.append("registered phase-map grid or replication count drifted")
    if payload.get("conditions") != list(runner.CONDITIONS):
        errors.append("topology conditions drifted")
    if payload.get("mutation_policy") != runner.MUTATION_POLICY:
        errors.append("mutation policy drifted")
    if payload.get("prior_seed_overlap") is not False:
        errors.append("prior seed isolation is not attested")
    expected = expected_keys(payload)
    observed: set[tuple[str, int, int, int]] = set()
    seed_by_block: dict[int, str] = {}
    expected_seed_by_block = {
        block: runner.seed_sha256(runner.phase_seed(block))
        for block in range(int(payload["blocks"]))
    }
    expected_policy_by_block = {
        block: hashlib.sha256(str(runner.phase_policy_seed(block)).encode()).hexdigest()
        for block in range(int(payload["blocks"]))
    }
    for row in payload.get("rows", []):
        family = str(row.get("family"))
        difficulty = int(row.get("n") if family == "smooth" else row.get("k"))
        key = (family, difficulty, int(row.get("budget")), int(row.get("block")))
        if key in observed:
            errors.append(f"duplicate topology triplet: {key}")
        observed.add(key)
        block = int(row.get("block"))
        seed_hash = str(row.get("seed_sha256"))
        if seed_hash != expected_seed_by_block.get(block):
            errors.append(f"unexpected held-out seed hash in block {block}")
        if row.get("policy_seed_sha256") != expected_policy_by_block.get(block):
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
                if exact is not (prefix == difficulty):
                    errors.append(f"Smooth exact flag mismatch at {key}/{condition}")
    missing = expected - observed
    extra = observed - expected
    if missing:
        errors.append(f"missing {len(missing)} topology triplets")
    if extra:
        errors.append(f"found {len(extra)} unexpected topology triplets")

    expected_references = {
        (k, block)
        for k in map(int, payload["rugged_k_values"])
        for block in range(int(payload["blocks"]))
    }
    references: set[tuple[int, int]] = set()
    for row in payload.get("rugged_random_references", []):
        key = (int(row.get("k")), int(row.get("block")))
        if key in references:
            errors.append(f"duplicate Rugged random reference: {key}")
        references.add(key)
        if not isinstance(row.get("random_sd"), (int, float)) or float(row["random_sd"]) <= 0:
            errors.append(f"invalid Rugged random SD: {key}")
        block_seed = seed_by_block.get(key[1])
        if block_seed is not None and row.get("seed_sha256") != block_seed:
            errors.append(f"reference seed drift: {key}")
    if references != expected_references:
        errors.append("Rugged random-reference matrix is incomplete")
    return errors


def descriptive_interval(values: list[float], label: str) -> tuple[float, float]:
    return bootstrap_mean_interval(
        values,
        label=f"descriptive:{label}",
        lower_probability=0.025,
    )


def summarize_rugged(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    indexed = {
        (int(row["k"]), int(row["budget"]), int(row["block"])): row
        for row in payload["rows"]
        if row["family"] == "rugged"
    }
    references = {
        (int(row["k"]), int(row["block"])): float(row["random_sd"])
        for row in payload["rugged_random_references"]
    }
    ks = tuple(map(int, payload["rugged_k_values"]))
    budgets = tuple(map(int, payload["budgets"]))
    blocks = range(int(payload["blocks"]))
    cell_count = len(ks) * len(budgets)
    one_sided_alpha = FAMILYWISE_ALPHA / (cell_count * 2)
    rows: list[dict[str, Any]] = []
    passing: list[dict[str, int]] = []
    for k in ks:
        for budget in budgets:
            contrasts: dict[str, Any] = {}
            gate_values: list[bool] = []
            for control, floor in (
                ("global_8", MULTI_GLOBAL_FLOOR_Z),
                ("partition_4", MULTI_PARTITION_FLOOR_Z),
            ):
                raw = []
                standardized = []
                for block in blocks:
                    item = indexed[(k, budget, block)]["conditions"]
                    difference = float(item["multi_island_4"]["best_score"]) - float(
                        item[control]["best_score"]
                    )
                    raw.append(difference)
                    standardized.append(difference / references[(k, block)])
                label = f"rugged:{k}:{budget}:multi-minus-{control}"
                raw_low, raw_high = descriptive_interval(raw, f"{label}:raw")
                z_low, z_high = descriptive_interval(standardized, f"{label}:z")
                ladder_low, _ = bootstrap_mean_interval(
                    standardized,
                    label=f"multiplicity:{label}",
                    lower_probability=one_sided_alpha,
                )
                passed = bool(
                    statistics.fmean(standardized) >= floor and ladder_low > 0
                )
                gate_values.append(passed)
                contrasts[f"multi_minus_{control.removesuffix('_8').removesuffix('_4')}"] = {
                    "mean_raw_difference": statistics.fmean(raw),
                    "descriptive_raw_ci": [raw_low, raw_high],
                    "mean_random_z_difference": statistics.fmean(standardized),
                    "descriptive_random_z_ci": [z_low, z_high],
                    "multiplicity_controlled_random_z_lower": ladder_low,
                    "practical_floor_random_z": floor,
                    "passes": passed,
                }
            passes = all(gate_values)
            row = {"k": k, "budget": budget, "contrasts": contrasts, "passes": passes}
            rows.append(row)
            if passes:
                passing.append({"k": k, "budget": budget})
    earliest_by_k = {
        str(k): next(
            (budget for budget in budgets if {"k": k, "budget": budget} in passing),
            None,
        )
        for k in ks
    }
    return rows, {
        "familywise_alpha": FAMILYWISE_ALPHA,
        "one_sided_alpha_per_contrast": one_sided_alpha,
        "tested_cells": cell_count,
        "passing_cells": passing,
        "earliest_passing_budget_by_k": earliest_by_k,
        "phase_region_observed": bool(passing and len(passing) < cell_count),
        "nonmonotonicity_allowed": True,
    }


def summarize_smooth(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    indexed = {
        (int(row["n"]), int(row["budget"]), int(row["block"])): row
        for row in payload["rows"]
        if row["family"] == "smooth"
    }
    sizes = tuple(map(int, payload["smooth_sizes"]))
    budgets = tuple(map(int, payload["budgets"]))
    blocks = range(int(payload["blocks"]))
    cell_count = len(sizes) * len(budgets)
    one_sided_alpha = FAMILYWISE_ALPHA / cell_count
    rows: list[dict[str, Any]] = []
    for n in sizes:
        for budget in budgets:
            global_minus_multi_prefix = []
            exact_solutions = {condition: 0 for condition in runner.CONDITIONS}
            mean_prefix = {condition: [] for condition in runner.CONDITIONS}
            for block in blocks:
                conditions = indexed[(n, budget, block)]["conditions"]
                for condition in runner.CONDITIONS:
                    result = conditions[condition]
                    mean_prefix[condition].append(int(result["best_prefix"]))
                    exact_solutions[condition] += int(bool(result["exact"]))
                global_minus_multi_prefix.append(
                    int(conditions["global_8"]["best_prefix"])
                    - int(conditions["multi_island_4"]["best_prefix"])
                )
            low, high = descriptive_interval(
                global_minus_multi_prefix,
                f"smooth:{n}:{budget}:global-minus-multi",
            )
            ladder_low, _ = bootstrap_mean_interval(
                global_minus_multi_prefix,
                label=f"smooth-multiplicity:{n}:{budget}:global-minus-multi",
                lower_probability=one_sided_alpha,
            )
            rows.append(
                {
                    "n": n,
                    "budget": budget,
                    "mean_best_prefix": {
                        condition: statistics.fmean(values)
                        for condition, values in mean_prefix.items()
                    },
                    "exact_solutions": exact_solutions,
                    "mean_global_minus_multi_prefix": statistics.fmean(
                        global_minus_multi_prefix
                    ),
                    "descriptive_global_minus_multi_prefix_ci": [low, high],
                    "multiplicity_controlled_global_minus_multi_prefix_lower": ladder_low,
                    "global_advantage_passes": ladder_low > 0,
                    "unsolved_all_conditions": not any(exact_solutions.values()),
                }
            )
    hard_rows = [row for row in rows if row["n"] >= 512]
    return rows, {
        "familywise_alpha": FAMILYWISE_ALPHA,
        "one_sided_alpha_per_cell": one_sided_alpha,
        "tested_cells": cell_count,
        "hard_smooth_sizes": [n for n in sizes if n >= 512],
        "all_hard_cells_unsolved": all(row["unsolved_all_conditions"] for row in hard_rows),
        "hard_cells_with_global_advantage": sum(
            row["global_advantage_passes"] for row in hard_rows
        ),
        "hard_cell_count": len(hard_rows),
    }


def analyze(payload: dict[str, Any], *, require_registered: bool) -> dict[str, Any]:
    errors = audit(payload, require_registered=require_registered)
    if errors:
        raise ValueError("; ".join(errors))
    rugged_rows, rugged_decision = summarize_rugged(payload)
    smooth_rows, smooth_decision = summarize_smooth(payload)
    return {
        "schema_version": 1,
        "source_fully_registered": bool(payload["fully_registered_run"]),
        "audit_passes": True,
        "bootstrap_repetitions": BOOTSTRAP_REPETITIONS,
        "rugged_phase_map": rugged_rows,
        "rugged_decision": rugged_decision,
        "smooth_phase_map": smooth_rows,
        "smooth_decision": smooth_decision,
        "claim_boundary": (
            "A passing Rugged phase region is evidence only for the frozen scripted "
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
    payload = json.loads(args.input.read_text())
    require_registered = not args.allow_reduced
    if args.allow_reduced and args.output == DEFAULT_OUTPUT:
        raise SystemExit("reduced analyses require a non-default output")
    try:
        result = analyze(payload, require_registered=require_registered)
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"phase-map audit failed: {exc}") from exc
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "rugged": result["rugged_decision"],
                "smooth": result["smooth_decision"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
