# EVOLVE-BLOCK-START
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: str) -> dict:
    with Path(path).open() as handle:
        return json.load(handle)


def dump_json(path: str, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def solution_score(selected_ids: list[str], candidates: dict[str, set[str]], feature_weights: dict[str, float]) -> float:
    covered = set()
    for candidate_id in selected_ids:
        covered.update(candidates[candidate_id])
    return float(sum(feature_weights[feature_id] for feature_id in covered))


def individual_feature_count_selection(budget: int, candidates: dict[str, set[str]]) -> list[str]:
    ranked = sorted(
        candidates.items(),
        key=lambda item: (-len(item[1]), item[0]),
    )
    selected = [candidate_id for candidate_id, _ in ranked[:budget]]
    selected.sort()
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description="Pure-Python starter solver for weighted coverage.")
    parser.add_argument("--prepared-input", required=True)
    parser.add_argument("--solution-output", required=True)
    args = parser.parse_args()

    prepared = load_json(args.prepared_input)
    budget = int(prepared["budget"])
    feature_weights = {key: float(value) for key, value in prepared["feature_weights"].items()}
    candidates = {
        candidate["candidate_id"]: set(candidate["covered_features"])
        for candidate in prepared["candidates"]
    }

    selected_ids = individual_feature_count_selection(budget, candidates)
    score = solution_score(selected_ids, candidates, feature_weights)
    solver = "individual_feature_count"

    dump_json(
        args.solution_output,
        {
            "selected_candidate_ids": selected_ids,
            "solver": solver,
            "predicted_score": round(score, 6),
        },
    )


if __name__ == "__main__":
    main()
# EVOLVE-BLOCK-END
