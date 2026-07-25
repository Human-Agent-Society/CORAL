#!/usr/bin/env python3
"""Analyze only integrity-valid hard-Smooth/Rugged scripted mechanism cells."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from experiments.multi_island_hard import analyze_threshold_v2 as base
from experiments.multi_island_hard import audit_threshold_v4_canary as common
from experiments.multi_island_hard import audit_threshold_v5_mechanism as integrity
from experiments.multi_island_hard import run_threshold_v5_mechanism as runner

ROOT = Path(__file__).resolve().parent
DIAGNOSTICS = ROOT / "threshold_v5_diagnostics.json"
REGISTERED_REPETITIONS = 8
BOUNDARY_EFFECT_FLOOR_RANDOM_Z = 0.25
MIGRATION_EFFECT_FLOOR_RANDOM_Z = 0.10
LADDER_FAMILYWISE_ALPHA = 0.05
LADDER_ONE_SIDED_ALPHA = LADDER_FAMILYWISE_ALPHA / len(
    runner.CONFIRMATORY_BUDGETS
)


def mean_hamming(candidates: list[str]) -> float:
    distances = [
        sum(left != right for left, right in zip(candidates[i], candidates[j], strict=True))
        / len(candidates[i])
        for i in range(len(candidates))
        for j in range(i + 1, len(candidates))
    ]
    return statistics.fmean(distances) if distances else 0.0


def diversity_at(
    records: list[dict[str, Any]],
    candidates: dict[str, str],
    count: int,
) -> float:
    latest: dict[str, str] = {}
    for record in records[:count]:
        commit = str(record["commit_hash"])
        latest[common.base_agent_id(str(record["agent_id"]))] = candidates[commit]
    return mean_hamming(list(latest.values()))


def collect(cell: dict[str, Any], budget: int) -> dict[str, Any]:
    run_dir = Path(cell["run_dir"])
    records = base.real_records(run_dir)
    candidates = common.source_candidates(
        run_dir,
        {str(record["commit_hash"]) for record in records},
    )
    scores = [float(record["score"]) for record in records]
    best = float("-inf")
    progress = []
    for score in scores:
        best = max(best, score)
        progress.append(best)
    traces, errors = common.load_traces(
        run_dir,
        attempts_per_agent=budget // 8,
    )
    if errors:
        raise ValueError(f"trace changed after audit: {errors}")
    task = str(cell["task"])
    return {
        "task": task,
        "condition": str(cell["condition"]),
        "repetition": int(cell["repetition"]),
        "budget": budget,
        "final_best": max(scores),
        "best_so_far_auc": statistics.fmean(progress),
        "solved_prefix": round(max(scores) * 512) if task == runner.SMOOTH_TASK else None,
        "midpoint_diversity": diversity_at(records, candidates, budget // 2),
        "final_diversity": diversity_at(records, candidates, budget),
        "unique_candidates": len(set(candidates.values())),
        "admission_recovery_submissions": sum(
            int(trace.get("admission_recovery_submissions", 0)) for trace in traces
        ),
        "migration_events": int(cell["migration_events"]),
    }


def rugged_random_references(
    selection: dict[str, int],
    path: Path = DIAGNOSTICS,
) -> dict[int, tuple[float, float]]:
    data = json.loads(path.read_text())
    if (
        not data.get("fully_registered_run")
        or not data.get("difficulty_gates", {}).get("heldout_difficulty_passes")
        or int(data.get("selected_k", -1)) != selection["k"]
    ):
        raise ValueError("v5 analysis requires passing registered held-out diagnostics")
    rows = [row for row in data.get("landscapes", []) if row.get("family") == "nk"]
    references = {
        int(row["seed_index"]) + 1: (
            float(row["random_mean"]),
            float(row["random_sd"]),
        )
        for row in rows
        if float(row.get("random_sd", 0)) > 0
    }
    if set(references) != set(range(1, REGISTERED_REPETITIONS + 1)):
        raise ValueError("v5 Rugged diagnostics do not cover all held-out seeds")
    return references


def rugged_random_scales(
    selection: dict[str, int],
    path: Path = DIAGNOSTICS,
) -> dict[int, float]:
    return {
        repetition: reference[1]
        for repetition, reference in rugged_random_references(selection, path).items()
    }


def bootstrap(
    values: list[float],
    label: str,
    *,
    tail_probability: float = 0.025,
) -> tuple[float, float]:
    if len(values) == 1:
        return values[0], values[0]
    if not 0 < tail_probability < 0.5:
        raise ValueError("bootstrap tail probability must be in (0, 0.5)")
    rng = random.Random(int.from_bytes(hashlib.sha256(label.encode()).digest()[:8], "big"))
    draws = sorted(
        statistics.fmean(rng.choice(values) for _ in values) for _ in range(10_000)
    )
    low = max(0, int(len(draws) * tail_probability) - 1)
    high = min(len(draws) - 1, int(len(draws) * (1 - tail_probability)) - 1)
    return draws[low], draws[high]


def contrasts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = {
        (row["task"], row["condition"], row["repetition"]): row for row in rows
    }
    grouped: defaultdict[tuple[str, str], list[float]] = defaultdict(list)
    grouped_random_z: defaultdict[tuple[str, str], list[float]] = defaultdict(list)
    for task in sorted({str(row["task"]) for row in rows}):
        repetitions = sorted(
            int(row["repetition"]) for row in rows if row["task"] == task and row["condition"] == "global_8"
        )
        for repetition in repetitions:
            multi = indexed[(task, "multi_island_4", repetition)]["final_best"]
            for control in ("global_8", "partition_4"):
                key = (task, f"multi_island_4_minus_{control}")
                reference = indexed[(task, control, repetition)]
                difference = float(multi) - float(reference["final_best"])
                grouped[key].append(difference)
                scale = reference.get("random_sd")
                if isinstance(scale, (int, float)) and float(scale) > 0:
                    grouped_random_z[key].append(difference / float(scale))
    output = []
    for (task, contrast), values in sorted(grouped.items()):
        low, high = bootstrap(values, f"v5:{task}:{contrast}")
        ladder_low, ladder_high = bootstrap(
            values,
            f"v5:{task}:{contrast}",
            tail_probability=LADDER_ONE_SIDED_ALPHA,
        )
        item = {
            "task": task,
            "contrast": contrast,
            "paired_repetitions": len(values),
            "mean_difference": statistics.fmean(values),
            "bootstrap_ci_low": low,
            "bootstrap_ci_high": high,
            "ladder_simultaneous_ci_low": ladder_low,
            "ladder_simultaneous_ci_high": ladder_high,
            "paired_differences": values,
        }
        z_values = grouped_random_z.get((task, contrast), [])
        if len(z_values) == len(values):
            z_low, z_high = bootstrap(
                z_values,
                f"v5-random-z:{task}:{contrast}",
            )
            z_ladder_low, z_ladder_high = bootstrap(
                z_values,
                f"v5-random-z:{task}:{contrast}",
                tail_probability=LADDER_ONE_SIDED_ALPHA,
            )
            item.update(
                {
                    "mean_random_z_difference": statistics.fmean(z_values),
                    "random_z_bootstrap_ci_low": z_low,
                    "random_z_bootstrap_ci_high": z_high,
                    "random_z_ladder_simultaneous_ci_low": z_ladder_low,
                    "random_z_ladder_simultaneous_ci_high": z_ladder_high,
                    "paired_random_z_differences": z_values,
                }
            )
        output.append(item)
    return output


def decision(
    rows: list[dict[str, Any]],
    paired: list[dict[str, Any]],
    *,
    budget: int,
    repetitions: int,
    selection: dict[str, int],
    registered_budget: bool,
) -> dict[str, Any]:
    """Apply the preregistered Rugged win and hard-Smooth falsification gates."""

    rugged_task = runner.RUGGED_TASKS[selection["k"]]

    def contrast(task: str, name: str) -> dict[str, Any] | None:
        return next(
            (
                row
                for row in paired
                if row["task"] == task and row["contrast"] == name
            ),
            None,
        )

    rugged_global = contrast(rugged_task, "multi_island_4_minus_global_8")
    rugged_partition = contrast(rugged_task, "multi_island_4_minus_partition_4")
    smooth_global = contrast(runner.SMOOTH_TASK, "multi_island_4_minus_global_8")
    required = (rugged_global, rugged_partition, smooth_global)
    ready = bool(
        registered_budget
        and budget in runner.CONFIRMATORY_BUDGETS
        and repetitions == REGISTERED_REPETITIONS
        and all(row is not None for row in required)
        and all(
            int(row["paired_repetitions"]) == REGISTERED_REPETITIONS
            for row in required
            if row is not None
        )
    )
    rugged_beats_global = bool(
        ready
        and rugged_global is not None
        and float(rugged_global["ladder_simultaneous_ci_low"]) > 0
        and float(rugged_global["mean_random_z_difference"])
        >= BOUNDARY_EFFECT_FLOOR_RANDOM_Z
        and float(rugged_global["random_z_ladder_simultaneous_ci_low"]) > 0
    )
    rugged_beats_partition = bool(
        ready
        and rugged_partition is not None
        and float(rugged_partition["ladder_simultaneous_ci_low"]) > 0
        and float(rugged_partition["mean_random_z_difference"])
        >= MIGRATION_EFFECT_FLOOR_RANDOM_Z
        and float(rugged_partition["random_z_ladder_simultaneous_ci_low"]) > 0
    )
    # The separate hard-Smooth control is supposed to falsify a generic
    # "harder tasks favor islands" explanation.  Keep the scale separate and
    # require the preregistered opposite direction; never subtract its effect
    # from the NK effect or pool the two families.
    smooth_global_beats_multi = bool(
        ready
        and smooth_global is not None
        and float(smooth_global["ladder_simultaneous_ci_high"]) < 0
    )
    smooth_rows = [row for row in rows if row["task"] == runner.SMOOTH_TASK]
    smooth_unsolved = bool(
        ready
        and len(smooth_rows)
        == REGISTERED_REPETITIONS * len(runner.CONDITIONS)
        and all(float(row["final_best"]) < 1.0 for row in smooth_rows)
    )
    return {
        "confirmatory_ready": ready,
        "registered_repetitions": REGISTERED_REPETITIONS,
        "ladder_familywise_alpha": LADDER_FAMILYWISE_ALPHA,
        "ladder_one_sided_alpha_per_budget": LADDER_ONE_SIDED_ALPHA,
        "uses_multiplicity_controlled_ladder_bounds": True,
        "boundary_effect_floor_random_z": BOUNDARY_EFFECT_FLOOR_RANDOM_Z,
        "migration_effect_floor_random_z": MIGRATION_EFFECT_FLOOR_RANDOM_Z,
        "rugged_beats_global": rugged_beats_global,
        "rugged_beats_partition": rugged_beats_partition,
        "hard_smooth_global_beats_multi": smooth_global_beats_multi,
        "hard_smooth_unsolved": smooth_unsolved,
        "cross_family_effect_pooling": False,
        "confirmatory_mechanism_threshold_passes": bool(
            rugged_beats_global
            and rugged_beats_partition
            and smooth_global_beats_multi
            and smooth_unsolved
        ),
        "requires_eight_paired_heldout_seeds": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=runner.RESULTS_ROOT)
    parser.add_argument("--budget", type=int, default=runner.registered_selection()["budget"])
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.results_root.resolve()
    budget_root = root if root.name == f"budget-{args.budget}" else root / f"budget-{args.budget}"
    integrity.require_budget_not_invalidated(budget_root)
    audit_path = budget_root / "scripted-mechanism-audit.json"
    audit = json.loads(audit_path.read_text())
    if (
        audit.get("valid_cells") != audit.get("expected_cells")
        or audit.get("matrix_errors")
        or int(audit.get("budget", -1)) != args.budget
        or int(audit.get("repetitions", -1)) != args.repetitions
        or bool(audit.get("registered_budget"))
        != bool(
            args.budget in runner.CONFIRMATORY_BUDGETS
            and "engineering-smoke" not in budget_root.parts
        )
    ):
        raise SystemExit("mechanism analysis requires a complete matching integrity audit")
    selection = runner.registered_selection()
    scales = rugged_random_scales(selection)
    rugged_task = runner.RUGGED_TASKS[selection["k"]]
    rows = [collect(cell, args.budget) for cell in audit["cells"]]
    for row in rows:
        row["random_sd"] = (
            scales[int(row["repetition"])] if row["task"] == rugged_task else None
        )
    paired = contrasts(rows)
    result = {
        "schema_version": 1,
        "budget": args.budget,
        "repetitions": args.repetitions,
        "registered_confirmatory_budget": bool(audit["registered_budget"]),
        "calibration_selected_anchor": args.budget == selection["budget"],
        "rows": rows,
        "contrasts": paired,
        "decision": decision(
            rows,
            paired,
            budget=args.budget,
            repetitions=args.repetitions,
            selection=selection,
            registered_budget=bool(audit["registered_budget"]),
        ),
        "interpretation": (
            "Scripted mechanism evidence only. One-seed phase-map differences are "
            "engineering estimates and cannot support the institutions claim."
        ),
    }
    output = args.output or budget_root / "scripted-mechanism-analysis.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["contrasts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
