# EVOLVE-BLOCK-START
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def load_json(path: str) -> dict:
    with Path(path).open() as handle:
        return json.load(handle)


def dump_json(path: str, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def rmse(values_a: list[float], values_b: list[float]) -> float:
    squared_error = 0.0
    for left, right in zip(values_a, values_b):
        squared_error += (left - right) ** 2
    return math.sqrt(squared_error / len(values_a))


def score_from_rmse(value: float, score_penalty_per_rmse: float) -> float:
    return max(0.0, 100.0 - score_penalty_per_rmse * value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pure-Python starter solver for torsion profile fitting.")
    parser.add_argument("--prepared-input", required=True)
    parser.add_argument("--solution-output", required=True)
    args = parser.parse_args()

    prepared = load_json(args.prepared_input)
    target_profile = [float(value) for value in prepared["target_relative_energies_kcal_per_mol"]]
    score_penalty_per_rmse = float(prepared.get("score_penalty_per_rmse", 250.0))

    best_candidate = None
    for candidate in prepared["candidate_profiles"]:
        if all(abs(float(candidate["term_scales"][term_name]) - 1.0) < 1e-9 for term_name in prepared["tunable_terms"]):
            best_candidate = candidate
            break

    if best_candidate is None:
        raise ValueError("Prepared input did not contain the default all-ones parameter setting.")

    best_rmse = rmse(
        [float(value) for value in best_candidate["relative_energies_kcal_per_mol"]],
        target_profile,
    )

    dump_json(
        args.solution_output,
        {
            "selected_candidate_id": best_candidate["candidate_id"],
            "term_scales": {term_name: 1.0 for term_name in prepared["tunable_terms"]},
            "predicted_rmse_kcal_per_mol": round(best_rmse, 6),
            "predicted_score": round(score_from_rmse(best_rmse, score_penalty_per_rmse), 6),
            "strategy": "default_force_field_scales",
        },
    )


if __name__ == "__main__":
    main()
# EVOLVE-BLOCK-END
