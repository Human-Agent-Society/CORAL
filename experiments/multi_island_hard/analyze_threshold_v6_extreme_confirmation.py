#!/usr/bin/env python3
"""Audit and analyze the independent extreme-cell confirmation run."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import analyze_threshold_v6_extreme_phase as discovery_analyzer
from experiments.multi_island_hard import analyze_threshold_v6_phase_map as base
from experiments.multi_island_hard import run_threshold_v6_extreme_confirmation as runner
from experiments.multi_island_hard import run_threshold_v6_extreme_phase as discovery_runner
from experiments.multi_island_hard import select_threshold_v6_extreme_confirmation as selector

ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = runner.DEFAULT_OUTPUT
DEFAULT_OUTPUT = ROOT / "threshold_v6_extreme_confirmation_analysis.json"
ONE_SIDED_ALPHA = 0.05


def audit(
    payload: dict[str, Any],
    *,
    require_registered: bool,
    selection: dict[str, Any] | None = None,
    selection_file_sha256: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("unexpected confirmation schema version")
    if require_registered and payload.get("fully_registered_run") is not True:
        errors.append("confirmation is not the fully registered run")
    if int(payload.get("rugged_n", -1)) != discovery_runner.RUGGED_N:
        errors.append("confirmation Rugged dimension drifted")
    if payload.get("conditions") != list(discovery_runner.CONDITIONS):
        errors.append("confirmation topology conditions drifted")
    if payload.get("mutation_policy") != discovery_runner.MUTATION_POLICY:
        errors.append("confirmation mutation policy drifted")
    if payload.get("prior_seed_overlap") is not False:
        errors.append("confirmation seed isolation is not attested")

    blocks = int(payload.get("blocks", 0))
    reference_samples = int(payload.get("reference_samples_per_block", 0))
    k = int(payload.get("k", -1))
    budget = int(payload.get("budget", -1))
    if require_registered:
        if blocks != selector.CONFIRMATION_BLOCKS:
            errors.append("confirmation block count drifted")
        if reference_samples != selector.CONFIRMATION_REFERENCE_SAMPLES:
            errors.append("confirmation reference-sample count drifted")
        if selection is None or selection_file_sha256 is None:
            errors.append("registered confirmation selection was not supplied")
        else:
            selected = selection.get("selected_cell", {})
            if k != int(selected.get("k", -2)) or budget != int(selected.get("budget", -2)):
                errors.append("confirmed cell differs from deterministic selection")
            if payload.get("discovery_source_sha256") != selection.get(
                "discovery_source_sha256"
            ):
                errors.append("confirmation discovery-source hash drifted")
            if payload.get("selection_file_sha256") != selection_file_sha256:
                errors.append("confirmation selection-file hash drifted")

    expected_seed = {
        block: runner.seed_sha256(runner.confirmation_seed(block))
        for block in range(blocks)
    }
    expected_policy = {
        block: hashlib.sha256(str(runner.confirmation_policy_seed(block)).encode()).hexdigest()
        for block in range(blocks)
    }
    observed: set[int] = set()
    for row in payload.get("rows", []):
        block = int(row.get("block", -1))
        if block in observed:
            errors.append(f"duplicate confirmation block: {block}")
        observed.add(block)
        if row.get("seed_sha256") != expected_seed.get(block):
            errors.append(f"unexpected confirmation seed hash in block {block}")
        if row.get("policy_seed_sha256") != expected_policy.get(block):
            errors.append(f"unexpected confirmation policy hash in block {block}")
        conditions = row.get("conditions", {})
        if set(conditions) != set(discovery_runner.CONDITIONS):
            errors.append(f"incomplete confirmation topology triplet in block {block}")
            continue
        for condition, result in conditions.items():
            score = result.get("best_score")
            if not isinstance(score, (int, float)) or not 0 <= float(score) <= 1:
                errors.append(f"invalid confirmation score in block {block}/{condition}")
    if observed != set(range(blocks)):
        errors.append("confirmation block matrix is incomplete")

    references: set[int] = set()
    for row in payload.get("rugged_random_references", []):
        block = int(row.get("block", -1))
        if block in references:
            errors.append(f"duplicate confirmation random reference: {block}")
        references.add(block)
        if row.get("seed_sha256") != expected_seed.get(block):
            errors.append(f"confirmation reference seed drift in block {block}")
        if not isinstance(row.get("random_sd"), (int, float)) or float(row["random_sd"]) <= 0:
            errors.append(f"invalid confirmation random SD in block {block}")
    if references != set(range(blocks)):
        errors.append("confirmation random-reference matrix is incomplete")
    return errors


def interval(
    values: list[float],
    *,
    label: str,
    lower_probability: float,
    repetitions: int,
) -> tuple[float, float]:
    return base.bootstrap_mean_interval(
        values,
        label=label,
        lower_probability=lower_probability,
        repetitions=repetitions,
    )


def analyze(
    payload: dict[str, Any],
    *,
    require_registered: bool,
    selection: dict[str, Any] | None = None,
    selection_file_sha256: str | None = None,
    bootstrap_repetitions: int = base.BOOTSTRAP_REPETITIONS,
) -> dict[str, Any]:
    errors = audit(
        payload,
        require_registered=require_registered,
        selection=selection,
        selection_file_sha256=selection_file_sha256,
    )
    if errors:
        raise ValueError("; ".join(errors))
    rows = {int(row["block"]): row for row in payload["rows"]}
    references = {
        int(row["block"]): row for row in payload["rugged_random_references"]
    }
    blocks = range(int(payload["blocks"]))

    performance: dict[str, Any] = {}
    for condition in discovery_runner.CONDITIONS:
        scores = [
            float(rows[block]["conditions"][condition]["best_score"])
            for block in blocks
        ]
        gains = [
            (scores[block] - float(references[block]["random_mean"]))
            / float(references[block]["random_sd"])
            for block in blocks
        ]
        performance[condition] = {
            "mean_final_best_score": statistics.fmean(scores),
            "mean_gain_over_random_z": statistics.fmean(gains),
        }

    contrasts: dict[str, Any] = {}
    effect_gates = []
    for control, floor in (
        ("global_8", selector.MULTI_GLOBAL_FLOOR_Z),
        ("partition_4", selector.MULTI_PARTITION_FLOOR_Z),
    ):
        standardized = [
            (
                float(rows[block]["conditions"]["multi_island_4"]["best_score"])
                - float(rows[block]["conditions"][control]["best_score"])
            )
            / float(references[block]["random_sd"])
            for block in blocks
        ]
        name = control.removesuffix("_8").removesuffix("_4")
        descriptive = interval(
            standardized,
            label=f"confirmation:{payload['k']}:{payload['budget']}:multi-minus-{name}:desc",
            lower_probability=0.025,
            repetitions=bootstrap_repetitions,
        )
        lower, _ = interval(
            standardized,
            label=f"confirmation:{payload['k']}:{payload['budget']}:multi-minus-{name}:one-sided",
            lower_probability=ONE_SIDED_ALPHA,
            repetitions=bootstrap_repetitions,
        )
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

    progress_floor = discovery_analyzer.iid_random_max_floor_z(int(payload["budget"]))
    minimum_progress = min(
        float(result["mean_gain_over_random_z"]) for result in performance.values()
    )
    progress_passes = minimum_progress >= progress_floor
    confirmation_passes = bool(all(effect_gates) and progress_passes)
    return {
        "schema_version": 1,
        "source_fully_registered": bool(payload["fully_registered_run"]),
        "audit_passes": True,
        "bootstrap_repetitions": bootstrap_repetitions,
        "selected_cell": {
            "n": int(payload["rugged_n"]),
            "k": int(payload["k"]),
            "affected_fraction": float(payload["affected_fraction"]),
            "budget": int(payload["budget"]),
        },
        "performance": performance,
        "contrasts": contrasts,
        "search_progress_gate": {
            "minimum_topology_gain_over_random_z": minimum_progress,
            "iid_random_search_expected_max_plus_margin_z": progress_floor,
            "passes": progress_passes,
        },
        "intersection_union_test": {
            "one_sided_alpha_each_component": ONE_SIDED_ALPHA,
            "multiplicity_rationale": (
                "The positive claim requires both component nulls to be rejected. Under "
                "the union null, rejecting both at alpha controls the conjunction claim "
                "at alpha without dividing alpha between the two components."
            ),
        },
        "confirmation_passes": confirmation_passes,
        "claim_boundary": (
            "A pass is independent confirmation only for the frozen scripted mechanism "
            "at the selected cell; the discovery surface locates the provisional phase "
            "region, and natural-agent/CORAL/real-task validation remains required."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--selection", type=Path, default=selector.DEFAULT_OUTPUT)
    parser.add_argument("--discovery", type=Path, default=selector.DEFAULT_INPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selection, _, selection_sha, _ = runner.load_registered_selection(
        args.selection,
        args.discovery,
    )
    payload = json.loads(args.input.read_text())
    try:
        result = analyze(
            payload,
            require_registered=True,
            selection=selection,
            selection_file_sha256=selection_sha,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"extreme confirmation audit failed: {exc}") from exc
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
