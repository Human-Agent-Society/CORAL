#!/usr/bin/env python3
"""Select one extreme-phase cell for independent held-out confirmation.

The selection rule is frozen before the extreme phase produces any topology
outcome.  Discovery effects are used only to select a cell; all confirmatory
claims use a fresh landscape-policy namespace.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import analyze_threshold_v6_extreme_phase as analyzer
from experiments.multi_island_hard import run_threshold_v6_extreme_phase as runner

ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = runner.DEFAULT_OUTPUT
DEFAULT_OUTPUT = ROOT / "threshold_v6_extreme_confirmation_selection.json"

CONFIRMATION_BLOCKS = 192
CONFIRMATION_REFERENCE_SAMPLES = runner.REGISTERED_REFERENCE_SAMPLES
CONFIRMATION_SEED_NAMESPACE = "threshold-v6-extreme-confirmation-heldout"
CONFIRMATION_POLICY_SEED_NAMESPACE = "threshold-v6-extreme-confirmation-policy"
MULTI_GLOBAL_FLOOR_Z = 0.25
MULTI_PARTITION_FLOOR_Z = 0.10


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def candidate_rows(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in analysis["rugged_phase_map"]:
        multi_global = float(
            row["contrasts"]["multi_minus_global"]["mean_random_z_difference"]
        )
        multi_partition = float(
            row["contrasts"]["multi_minus_partition"]["mean_random_z_difference"]
        )
        effect_margin = min(
            multi_global - MULTI_GLOBAL_FLOOR_Z,
            multi_partition - MULTI_PARTITION_FLOOR_Z,
        )
        progress_margin = float(row["minimum_topology_gain_over_random_z"]) - float(
            row["iid_random_search_expected_max_plus_margin_z"]
        )
        eligible = bool(
            multi_global >= MULTI_GLOBAL_FLOOR_Z
            and multi_partition >= MULTI_PARTITION_FLOOR_Z
            and row["search_progress_gate"]
        )
        rows.append(
            {
                "k": int(row["k"]),
                "budget": int(row["budget"]),
                "discovery_multi_minus_global_mean_random_z": multi_global,
                "discovery_multi_minus_partition_mean_random_z": multi_partition,
                "discovery_effect_margin_random_z": effect_margin,
                "discovery_progress_margin_random_z": progress_margin,
                "discovery_point_gate_eligible": eligible,
            }
        )
    if not rows:
        raise ValueError("extreme discovery analysis has no Rugged cells")
    return rows


def choose_candidate(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    eligible = [row for row in rows if row["discovery_point_gate_eligible"]]
    if eligible:
        # Strongest joint surplus is most likely to survive independent replication.
        # Lower K and lower budget are deterministic tie-breakers only.
        selected = max(
            eligible,
            key=lambda row: (
                row["discovery_effect_margin_random_z"],
                row["discovery_progress_margin_random_z"],
                -row["k"],
                -row["budget"],
            ),
        )
        return selected, "maximum_joint_effect_margin_among_point_gate_eligible_cells"
    selected = max(
        rows,
        key=lambda row: (
            min(
                row["discovery_effect_margin_random_z"],
                row["discovery_progress_margin_random_z"],
            ),
            row["discovery_effect_margin_random_z"],
            row["discovery_progress_margin_random_z"],
            -row["k"],
            -row["budget"],
        ),
    )
    return selected, "maximum_minimum_effect_and_progress_margin_fallback"


def build_selection(
    discovery: dict[str, Any],
    *,
    discovery_sha256: str,
) -> dict[str, Any]:
    analysis = analyzer.analyze(discovery, require_registered=True)
    rows = candidate_rows(analysis)
    selected, reason = choose_candidate(rows)
    return {
        "schema_version": 1,
        "purpose": "blindly select one extreme Rugged cell for fresh-seed confirmation",
        "discovery_source_sha256": discovery_sha256,
        "discovery_source_fully_registered": True,
        "selection_rule": (
            "Prefer cells whose discovery point estimates clear both practical floors and "
            "whose three topologies clear the progress gate; maximize the smaller effect "
            "surplus, then progress surplus, then prefer lower K and budget. If none are "
            "eligible, maximize the smaller of effect and progress surplus with the same "
            "deterministic tie-breakers. Discovery confidence bounds never determine selection."
        ),
        "selection_reason": reason,
        "selected_cell": selected,
        "confirmation_design": {
            "blocks": CONFIRMATION_BLOCKS,
            "reference_samples_per_block": CONFIRMATION_REFERENCE_SAMPLES,
            "conditions": list(runner.CONDITIONS),
            "multi_minus_global_practical_floor_random_z": MULTI_GLOBAL_FLOOR_Z,
            "multi_minus_partition_practical_floor_random_z": MULTI_PARTITION_FLOOR_Z,
            "seed_namespace": CONFIRMATION_SEED_NAMESPACE,
            "policy_seed_namespace": CONFIRMATION_POLICY_SEED_NAMESPACE,
        },
        "claim_boundary": (
            "The 64-block surface is discovery/selection evidence. Only the independent "
            "192-block confirmation can support a positive scripted-mechanism claim."
        ),
    }


def validate_selection(
    selection: dict[str, Any],
    *,
    discovery: dict[str, Any],
    discovery_sha256: str,
) -> None:
    expected = build_selection(discovery, discovery_sha256=discovery_sha256)
    if selection != expected:
        raise ValueError("confirmation selection does not match the registered deterministic rule")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    discovery = json.loads(args.input.read_text())
    selection = build_selection(discovery, discovery_sha256=file_sha256(args.input))
    args.output.write_text(json.dumps(selection, indent=2) + "\n")
    print(json.dumps(selection, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
