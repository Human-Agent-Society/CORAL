from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
from collections import Counter
from pathlib import Path


def load_json(path: str) -> dict:
    with Path(path).open() as handle:
        return json.load(handle)


def dump_json(path: str, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def _import_chemistry_stack():
    original_version = metadata.version

    def patched_version(name: str) -> str:
        if name == "openff.toolkit":
            try:
                return original_version(name)
            except metadata.PackageNotFoundError:
                return "local"
        return original_version(name)

    metadata.version = patched_version
    try:
        from openff.toolkit import ForceField, Molecule
    except Exception as exc:
        raise RuntimeError("Task 01 prepare requires an environment with openff-toolkit installed.") from exc
    finally:
        metadata.version = original_version

    return {"ForceField": ForceField, "Molecule": Molecule}


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


def parameter_ids_from_labels(molecule_labels: dict) -> set[str]:
    parameter_ids: set[str] = set()
    for handler_name, assignments in molecule_labels.items():
        for assignment in assignments.values():
            if isinstance(assignment, list):
                for parameter in assignment:
                    parameter_ids.add(f"{handler_name}:{parameter.id}")
            else:
                parameter_ids.add(f"{handler_name}:{assignment.id}")
    return parameter_ids


def exact_maximum_coverage_solution(budget: int, candidates: list[dict], feature_weights: dict[str, float]) -> tuple[float, list[str]]:
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp

    candidate_ids = [candidate["candidate_id"] for candidate in candidates]
    features = sorted(feature_weights)
    feature_index = {feature_id: index for index, feature_id in enumerate(features)}

    num_candidate_vars = len(candidate_ids)
    num_feature_vars = len(features)
    num_variables = num_candidate_vars + num_feature_vars

    objective = np.zeros(num_variables)
    for feature_id, weight in feature_weights.items():
        objective[num_candidate_vars + feature_index[feature_id]] = -float(weight)

    integrality = np.ones(num_variables, dtype=int)
    bounds = Bounds(np.zeros(num_variables), np.ones(num_variables))

    rows = []
    lower_bounds = []
    upper_bounds = []

    budget_row = np.zeros(num_variables)
    budget_row[:num_candidate_vars] = 1.0
    rows.append(budget_row)
    lower_bounds.append(-np.inf)
    upper_bounds.append(float(budget))

    coverers_by_feature = {feature_id: [] for feature_id in features}
    for candidate_index, candidate in enumerate(candidates):
        for feature_id in candidate["covered_features"]:
            coverers_by_feature[feature_id].append(candidate_index)

    for feature_id in features:
        row = np.zeros(num_variables)
        row[num_candidate_vars + feature_index[feature_id]] = 1.0
        for candidate_index in coverers_by_feature[feature_id]:
            row[candidate_index] -= 1.0
        rows.append(row)
        lower_bounds.append(-np.inf)
        upper_bounds.append(0.0)

    result = milp(
        c=objective,
        constraints=LinearConstraint(
            np.vstack(rows),
            np.asarray(lower_bounds, dtype=float),
            np.asarray(upper_bounds, dtype=float),
        ),
        integrality=integrality,
        bounds=bounds,
    )
    if not result.success:
        raise RuntimeError(f"Exact maximum-coverage MILP failed with status {result.status}.")

    selected_ids = [
        candidate_ids[index]
        for index, value in enumerate(result.x[:num_candidate_vars])
        if value > 0.5
    ]
    selected_ids.sort()
    return float(-result.fun), selected_ids


def prepare(raw_task_path: str, prepared_output_path: str) -> None:
    raw = load_json(raw_task_path)
    chem = _import_chemistry_stack()
    ForceField = chem["ForceField"]
    Molecule = chem["Molecule"]
    force_field = ForceField(raw["force_field"])

    candidates = []
    frequency = Counter()
    for index, record in enumerate(raw["molecules"]):
        molecule = Molecule.from_smiles(record["smiles"], allow_undefined_stereo=record.get("allow_undefined_stereo", False))
        molecule.name = record.get("name", record["smiles"])
        covered_features = sorted(parameter_ids_from_labels(force_field.label_molecules(molecule.to_topology())[0]))
        frequency.update(covered_features)
        candidates.append(
            {
                "candidate_id": f"mol_{index:03d}",
                "name": molecule.name,
                "smiles": record["smiles"],
                "covered_features": covered_features,
            }
        )

    rarity_weight_exponent = float(raw.get("rarity_weight_exponent", 2.0))
    feature_weights = {
        feature_id: 1.0 / (count ** rarity_weight_exponent)
        for feature_id, count in frequency.items()
    }
    prepared = {
        "task_name": raw["task_name"],
        "budget": int(raw["budget"]),
        "feature_weights": feature_weights,
        "candidates": candidates,
        "metadata": {
            "force_field": raw["force_field"],
            "num_candidates": len(candidates),
            "num_features": len(feature_weights),
            "rarity_weight_exponent": rarity_weight_exponent,
        },
    }
    dump_json(prepared_output_path, prepared)


def evaluate(prepared_input_path: str, solution_path: str, result_output_path: str) -> None:
    prepared = load_json(prepared_input_path)
    solution = load_json(solution_path)

    feature_weights = {key: float(value) for key, value in prepared["feature_weights"].items()}
    candidates = {candidate["candidate_id"]: set(candidate["covered_features"]) for candidate in prepared["candidates"]}
    selected_ids = list(solution.get("selected_candidate_ids", []))

    invalid_ids = [candidate_id for candidate_id in selected_ids if candidate_id not in candidates]
    unique_ids = []
    seen = set()
    for candidate_id in selected_ids:
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        unique_ids.append(candidate_id)

    budget = int(prepared["budget"])
    budget_respected = len(unique_ids) <= budget
    valid = (not invalid_ids) and budget_respected

    covered = set()
    if valid:
        for candidate_id in unique_ids:
            covered.update(candidates[candidate_id])
        score = solution_score(unique_ids, candidates, feature_weights)
    else:
        score = 0.0

    baseline_ids = individual_feature_count_selection(budget, candidates)
    baseline_score = solution_score(baseline_ids, candidates, feature_weights)
    exact_optimal_score, exact_optimal_ids = exact_maximum_coverage_solution(
        budget,
        prepared["candidates"],
        feature_weights,
    )

    total_feature_weight_upper_bound = float(sum(feature_weights.values()))
    certified_upper_bound = exact_optimal_score
    best_known_lower_bound = exact_optimal_score

    result = {
        "task_name": prepared["task_name"],
        "valid": valid,
        "budget_respected": budget_respected,
        "invalid_candidate_ids": invalid_ids,
        "selected_candidate_ids": unique_ids,
        "covered_feature_count": len(covered),
        "score": round(score, 6),
        "baseline_reference_score": round(baseline_score, 6),
        "baseline_reference_selected_candidate_ids": baseline_ids,
        "exact_optimal_score": round(exact_optimal_score, 6),
        "exact_optimal_selected_candidate_ids": exact_optimal_ids,
        "best_known_lower_bound": round(best_known_lower_bound, 6),
        "certified_upper_bound": round(certified_upper_bound, 6),
        "absolute_theoretical_upper_bound": round(total_feature_weight_upper_bound, 6),
        "gap_to_certified_upper_bound": round(max(0.0, certified_upper_bound - score), 6),
        "relative_gap_to_certified_upper_bound": round(max(0.0, certified_upper_bound - score) / certified_upper_bound, 6) if certified_upper_bound > 0 else None,
        "gap_to_exact_optimal": round(max(0.0, exact_optimal_score - score), 6),
        "relative_gap_to_exact_optimal": round(max(0.0, exact_optimal_score - score) / exact_optimal_score, 6) if exact_optimal_score > 0 else None,
    }
    dump_json(result_output_path, result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare and evaluate Task 01.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--raw-task", required=True)
    prepare_parser.add_argument("--prepared-output", required=True)

    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--prepared-input", required=True)
    evaluate_parser.add_argument("--solution", required=True)
    evaluate_parser.add_argument("--result-output", required=True)

    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.raw_task, args.prepared_output)
    else:
        evaluate(args.prepared_input, args.solution, args.result_output)


if __name__ == "__main__":
    main()
