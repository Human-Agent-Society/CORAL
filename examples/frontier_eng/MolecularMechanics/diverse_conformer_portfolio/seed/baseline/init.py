# EVOLVE-BLOCK-START
from __future__ import annotations

import argparse
import itertools
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


def node_reward(relative_energy: float, energy_weight: float, energy_cap: float) -> float:
    return energy_weight * max(0.0, energy_cap - relative_energy)


def pair_reward(rmsd: float, diversity_weight: float, rmsd_cap: float, diversity_exponent: float) -> float:
    return diversity_weight * (min(rmsd, rmsd_cap) ** diversity_exponent)


def subset_score(indices: tuple[int, ...], relative_energies: list[float], rmsd_matrix: list[list[float]], energy_weight: float, diversity_weight: float, energy_cap: float, rmsd_cap: float, diversity_exponent: float) -> float:
    score = 0.0
    for index in indices:
        score += node_reward(relative_energies[index], energy_weight, energy_cap)
    for left, right in itertools.combinations(indices, 2):
        score += pair_reward(rmsd_matrix[left][right], diversity_weight, rmsd_cap, diversity_exponent)
    return score


def solve_molecule(molecule: dict, portfolio_size: int, energy_weight: float, diversity_weight: float, energy_cap: float, rmsd_cap: float, diversity_exponent: float) -> tuple[list[str], float, str]:
    conformers = molecule["conformers"]
    relative_energies = [float(item["relative_energy_kcal_per_mol"]) for item in conformers]
    rmsd_matrix = molecule["pairwise_rmsd_angstrom"]
    seed_index = min(range(len(relative_energies)), key=relative_energies.__getitem__)
    ranked_indices = sorted(
        range(len(relative_energies)),
        key=lambda index: (float(rmsd_matrix[seed_index][index]), relative_energies[index], index),
    )
    selected_indices = sorted(ranked_indices[:portfolio_size])
    score = subset_score(
        tuple(selected_indices),
        relative_energies,
        rmsd_matrix,
        energy_weight,
        diversity_weight,
        energy_cap,
        rmsd_cap,
        diversity_exponent,
    )
    return [conformers[index]["conformer_id"] for index in selected_indices], score, "closest_to_lowest_energy"


def main() -> None:
    parser = argparse.ArgumentParser(description="Pure-Python starter solver for diverse conformer portfolio.")
    parser.add_argument("--prepared-input", required=True)
    parser.add_argument("--solution-output", required=True)
    args = parser.parse_args()

    prepared = load_json(args.prepared_input)
    portfolio_size = int(prepared["portfolio_size"])
    energy_weight = float(prepared["energy_weight"])
    diversity_weight = float(prepared["diversity_weight"])
    energy_cap = float(prepared["energy_cap_kcal_per_mol"])
    rmsd_cap = float(prepared["rmsd_cap_angstrom"])
    diversity_exponent = float(prepared.get("diversity_reward_exponent", 2.0))

    selected_conformer_ids: dict[str, list[str]] = {}
    solver_by_molecule: dict[str, str] = {}
    predicted_total_score = 0.0

    for molecule in prepared["molecules"]:
        chosen_ids, score, solver = solve_molecule(
            molecule,
            portfolio_size,
            energy_weight,
            diversity_weight,
            energy_cap,
            rmsd_cap,
            diversity_exponent,
        )
        selected_conformer_ids[molecule["molecule_id"]] = chosen_ids
        solver_by_molecule[molecule["molecule_id"]] = solver
        predicted_total_score += score

    dump_json(
        args.solution_output,
        {
            "selected_conformer_ids": selected_conformer_ids,
            "solver_by_molecule": solver_by_molecule,
            "predicted_total_score": round(predicted_total_score, 6),
        },
    )


if __name__ == "__main__":
    main()
# EVOLVE-BLOCK-END
