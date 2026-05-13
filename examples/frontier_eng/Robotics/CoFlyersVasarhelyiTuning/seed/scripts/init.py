# EVOLVE-BLOCK-START
"""Baseline submission for the original CoFlyers Vasarhelyi tuning cases.

This benchmark is based on the released `params_for_parallel` parameter files from
CoFlyers' Prototype_Simulator. The candidate must implement `solve(problem)` and
return tuned Vasarhelyi parameters for the provided case.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PARAMETER_KEYS = [
    "r_rep_0",
    "p_rep",
    "r_frict_0",
    "c_frict",
    "v_frict",
    "p_frict",
    "a_frict",
    "r_shill_0",
    "v_shill",
    "p_shill",
    "a_shill",
]

# DO NOT MODIFY: these bounds reflect the physical and numerical ranges of the original CoFlyers parameters, and the evaluator relies on them for clipping and validation.
PARAMETER_BOUNDS = {
    "r_rep_0": (0.05, 4.0),
    "p_rep": (0.01, 2.0),
    "r_frict_0": (0.2, 12.0),
    "c_frict": (0.001, 1.5),
    "v_frict": (0.001, 1.5),
    "p_frict": (0.05, 12.0),
    "a_frict": (0.001, 1.5),
    "r_shill_0": (0.05, 2.5),
    "v_shill": (0.05, 3.0),
    "p_shill": (0.05, 12.0),
    "a_shill": (0.001, 1.5),
}


# DO NOT MODIFY: both the evaluator and the baseline rely on the same original case list.
def load_reference_cases() -> dict[str, Any]:
    candidates = [
        Path(__file__).resolve().parent.parent / "references" / "coflyers_cases.json",
        Path(__file__).resolve().parent / "references" / "coflyers_cases.json",
    ]
    for path in candidates:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError("references/coflyers_cases.json not found")


# DO NOT MODIFY: the returned schema must remain compatible with `verification/evaluator.py`.
def merge_and_clip_params(baseline_params: dict[str, float], updates: dict[str, Any] | None) -> dict[str, float]:
    merged = {key: float(baseline_params[key]) for key in baseline_params}
    if updates:
        for key in PARAMETER_KEYS:
            if key in updates:
                lo, hi = PARAMETER_BOUNDS[key]
                merged[key] = min(max(float(updates[key]), lo), hi)
    return merged


# MODIFIABLE: this defines the most conservative reference solution—directly return the case parameters from the original CoFlyers repository.
def baseline_solve(problem: dict[str, Any]) -> dict[str, Any]:
    baseline_params = problem["baseline_params"]
    return {
        "params": merge_and_clip_params(baseline_params, None),
        "submission_kind": "params",
    }


# MODIFIABLE: you can locally tune `problem["baseline_params"]` here and return improved `params`.
def solve(problem: dict[str, Any]) -> dict[str, Any]:
    return baseline_solve(problem)


# EVOLVE-BLOCK-END


def main() -> int:
    payload = load_reference_cases()
    preview = {}
    for case in payload["cases"]:
        problem = {
            "case_id": case["case_id"],
            "baseline_params": case["baseline_params"],
            "global_config": payload["global_config"],
        }
        preview[case["case_id"]] = solve(problem)
    print(json.dumps(preview, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
