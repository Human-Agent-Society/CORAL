from __future__ import annotations

import argparse
import json
import itertools
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


def closest_to_lowest_energy_indices(molecule: dict, portfolio_size: int) -> list[int]:
    relative_energies = [float(item["relative_energy_kcal_per_mol"]) for item in molecule["conformers"]]
    seed_index = min(range(len(relative_energies)), key=relative_energies.__getitem__)
    ranked_indices = sorted(
        range(len(relative_energies)),
        key=lambda index: (
            float(molecule["pairwise_rmsd_angstrom"][seed_index][index]),
            relative_energies[index],
            index,
        ),
    )
    return sorted(ranked_indices[:portfolio_size])


def molecule_upper_bound_estimate(molecule: dict, portfolio_size: int, energy_weight: float, diversity_weight: float, energy_cap: float, rmsd_cap: float, diversity_exponent: float) -> float:
    conformers = molecule["conformers"]
    node_rewards = sorted(
        (node_reward(float(conformer["relative_energy_kcal_per_mol"]), energy_weight, energy_cap) for conformer in conformers),
        reverse=True,
    )
    pair_rewards = []
    for left, right in itertools.combinations(range(len(conformers)), 2):
        pair_rewards.append(pair_reward(float(molecule["pairwise_rmsd_angstrom"][left][right]), diversity_weight, rmsd_cap, diversity_exponent))
    pair_rewards.sort(reverse=True)

    return float(sum(node_rewards[:portfolio_size]) + sum(pair_rewards[: math.comb(portfolio_size, 2)]))


def score_selection(molecule: dict, selected_ids: list[str], portfolio_size: int, energy_weight: float, diversity_weight: float, energy_cap: float, rmsd_cap: float, diversity_exponent: float) -> tuple[bool, float, dict]:
    conformers = molecule["conformers"]
    index_by_id = {conformer["conformer_id"]: index for index, conformer in enumerate(conformers)}

    invalid_ids = [conformer_id for conformer_id in selected_ids if conformer_id not in index_by_id]
    unique_ids: list[str] = []
    seen = set()
    for conformer_id in selected_ids:
        if conformer_id in seen:
            continue
        seen.add(conformer_id)
        unique_ids.append(conformer_id)

    valid = (not invalid_ids) and len(unique_ids) == portfolio_size

    score = 0.0
    if valid:
        indices = [index_by_id[conformer_id] for conformer_id in unique_ids]
        for index in indices:
            score += node_reward(float(conformers[index]["relative_energy_kcal_per_mol"]), energy_weight, energy_cap)
        for i, left in enumerate(indices):
            for right in indices[i + 1 :]:
                score += pair_reward(float(molecule["pairwise_rmsd_angstrom"][left][right]), diversity_weight, rmsd_cap, diversity_exponent)

    diagnostics = {
        "selected_conformer_ids": unique_ids,
        "invalid_conformer_ids": invalid_ids,
        "selection_size": len(unique_ids),
        "required_selection_size": portfolio_size,
        "valid": valid,
        "score": round(score, 6),
    }
    return valid, score, diagnostics


def _import_chemistry_stack():
    import importlib.metadata as metadata

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
        import numpy as np
        import openmm
        from openmm import unit as openmm_unit
        from openff.toolkit import ForceField, Molecule, unit
        from openff.units.openmm import from_openmm, to_openmm
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except Exception as exc:
        raise RuntimeError(
            "Task 02 requires an environment with openff-toolkit, openff-units, rdkit, openmm, and numpy."
        ) from exc
    finally:
        metadata.version = original_version

    return {
        "AllChem": AllChem,
        "Chem": Chem,
        "ForceField": ForceField,
        "Molecule": Molecule,
        "from_openmm": from_openmm,
        "np": np,
        "openmm": openmm,
        "openmm_unit": openmm_unit,
        "to_openmm": to_openmm,
        "unit": unit,
    }


def _build_simulation(force_field, molecule, openmm, openmm_unit):
    topology = molecule.to_topology()
    system = force_field.create_openmm_system(topology, charge_from_molecules=[molecule])
    integrator = openmm.VerletIntegrator(1.0 * openmm_unit.femtoseconds)
    platform = openmm.Platform.getPlatformByName("Reference")
    return openmm.app.Simulation(topology.to_openmm(), system, integrator, platform)


def _evaluate_conformer(simulation, conformer, minimize, openmm, openmm_unit, from_openmm, to_openmm, unit):
    simulation.context.setPositions(to_openmm(conformer))
    if minimize:
        openmm.LocalEnergyMinimizer.minimize(simulation.context)
    state = simulation.context.getState(getEnergy=True, getPositions=True)
    energy = state.getPotentialEnergy().value_in_unit(openmm_unit.kilocalorie_per_mole)
    positions = from_openmm(state.getPositions(asNumpy=True)).to(unit.angstrom)
    return float(energy), positions


def _pairwise_rmsd_matrix(molecule, Chem, AllChem):
    rdkit_molecule = Chem.RemoveHs(molecule.to_rdkit())
    conformer_ids = [conformer.GetId() for conformer in rdkit_molecule.GetConformers()]
    size = len(conformer_ids)
    matrix = [[0.0 for _ in range(size)] for _ in range(size)]
    for left in range(size):
        for right in range(left + 1, size):
            value = float(AllChem.GetBestRMS(rdkit_molecule, rdkit_molecule, conformer_ids[left], conformer_ids[right]))
            matrix[left][right] = value
            matrix[right][left] = value
    return matrix


def prepare(raw_task_path: str, prepared_output_path: str) -> None:
    raw = load_json(raw_task_path)
    chem = _import_chemistry_stack()

    ForceField = chem["ForceField"]
    Molecule = chem["Molecule"]
    unit = chem["unit"]
    openmm = chem["openmm"]
    openmm_unit = chem["openmm_unit"]
    from_openmm = chem["from_openmm"]
    to_openmm = chem["to_openmm"]
    Chem = chem["Chem"]
    AllChem = chem["AllChem"]

    force_field = ForceField(raw["force_field"])
    n_conformers = int(raw["conformer_generation"]["n_conformers"])
    rms_cutoff = float(raw["conformer_generation"]["rms_cutoff_angstrom"]) * unit.angstrom
    minimize = bool(raw["conformer_generation"].get("minimize", True))

    prepared_molecules = []
    for index, record in enumerate(raw["molecules"]):
        molecule = Molecule.from_smiles(record["smiles"], allow_undefined_stereo=record.get("allow_undefined_stereo", False))
        molecule.name = record.get("name", record["smiles"])
        molecule.generate_conformers(n_conformers=n_conformers, rms_cutoff=rms_cutoff)
        molecule.assign_partial_charges(partial_charge_method="gasteiger")

        if molecule.n_conformers < int(raw["portfolio_size"]):
            raise ValueError(
                f"Molecule {molecule.name!r} only generated {molecule.n_conformers} conformers, "
                f"but portfolio_size={raw['portfolio_size']}."
            )

        simulation = _build_simulation(force_field, molecule, openmm, openmm_unit)
        minimized_molecule = Molecule(molecule)
        minimized_molecule.conformers.clear()
        absolute_energies = []
        conformer_records = []

        for conformer_index, conformer in enumerate(molecule.conformers):
            energy, minimized_positions = _evaluate_conformer(
                simulation,
                conformer,
                minimize,
                openmm,
                openmm_unit,
                from_openmm,
                to_openmm,
                unit,
            )
            absolute_energies.append(energy)
            minimized_molecule.add_conformer(minimized_positions)
            conformer_records.append(
                {
                    "conformer_id": f"{record.get('molecule_id', f'mol_{index:03d}')}_conf_{conformer_index:03d}",
                    "absolute_energy_kcal_per_mol": round(energy, 6),
                }
            )

        reference_energy = min(absolute_energies)
        for conformer_record, absolute_energy in zip(conformer_records, absolute_energies):
            conformer_record["relative_energy_kcal_per_mol"] = round(absolute_energy - reference_energy, 6)

        prepared_molecules.append(
            {
                "molecule_id": record.get("molecule_id", f"mol_{index:03d}"),
                "name": molecule.name,
                "smiles": record["smiles"],
                "num_generated_conformers": molecule.n_conformers,
                "conformers": conformer_records,
                "pairwise_rmsd_angstrom": _pairwise_rmsd_matrix(minimized_molecule, Chem, AllChem),
            }
        )

    prepared = {
        "task_name": raw["task_name"],
        "portfolio_size": int(raw["portfolio_size"]),
        "energy_weight": float(raw["energy_weight"]),
        "diversity_weight": float(raw["diversity_weight"]),
        "energy_cap_kcal_per_mol": float(raw["energy_cap_kcal_per_mol"]),
        "rmsd_cap_angstrom": float(raw["rmsd_cap_angstrom"]),
        "diversity_reward_exponent": float(raw.get("diversity_reward_exponent", 2.0)),
        "molecules": prepared_molecules,
        "metadata": {
            "force_field": raw["force_field"],
            "conformer_generation": raw["conformer_generation"],
            "charge_method": "gasteiger",
        },
    }
    dump_json(prepared_output_path, prepared)


def evaluate(prepared_input_path: str, solution_path: str, result_output_path: str) -> None:
    prepared = load_json(prepared_input_path)
    solution = load_json(solution_path)

    portfolio_size = int(prepared["portfolio_size"])
    energy_weight = float(prepared["energy_weight"])
    diversity_weight = float(prepared["diversity_weight"])
    energy_cap = float(prepared["energy_cap_kcal_per_mol"])
    rmsd_cap = float(prepared["rmsd_cap_angstrom"])
    diversity_exponent = float(prepared.get("diversity_reward_exponent", 2.0))
    submitted = solution.get("selected_conformer_ids", {})

    overall_valid = True
    total_score = 0.0
    molecule_results = []
    baseline_total_score = 0.0
    certified_upper_bound = 0.0

    for molecule in prepared["molecules"]:
        selected_ids = list(submitted.get(molecule["molecule_id"], []))
        valid, score, diagnostics = score_selection(
            molecule,
            selected_ids,
            portfolio_size,
            energy_weight,
            diversity_weight,
            energy_cap,
            rmsd_cap,
            diversity_exponent,
        )
        overall_valid = overall_valid and valid
        total_score += score

        relative_energies = [float(item["relative_energy_kcal_per_mol"]) for item in molecule["conformers"]]
        rmsd_matrix = molecule["pairwise_rmsd_angstrom"]
        baseline_indices = closest_to_lowest_energy_indices(molecule, portfolio_size)
        baseline_score = subset_score(
            tuple(baseline_indices),
            relative_energies,
            rmsd_matrix,
            energy_weight,
            diversity_weight,
            energy_cap,
            rmsd_cap,
            diversity_exponent,
        )
        baseline_total_score += baseline_score
        molecule_upper_bound = molecule_upper_bound_estimate(
            molecule,
            portfolio_size,
            energy_weight,
            diversity_weight,
            energy_cap,
            rmsd_cap,
            diversity_exponent,
        )
        certified_upper_bound += molecule_upper_bound
        molecule_results.append(
            {
                "molecule_id": molecule["molecule_id"],
                "name": molecule["name"],
                **diagnostics,
                "baseline_reference_score": round(baseline_score, 6),
                "baseline_reference_selected_conformer_ids": [molecule["conformers"][index]["conformer_id"] for index in baseline_indices],
                "certified_upper_bound": round(molecule_upper_bound, 6),
                "gap_to_certified_upper_bound": round(max(0.0, molecule_upper_bound - score), 6),
            }
        )

    absolute_theoretical_upper_bound = len(prepared["molecules"]) * (
        portfolio_size * energy_weight * energy_cap
        + math.comb(portfolio_size, 2) * diversity_weight * (rmsd_cap ** diversity_exponent)
    )
    effective_score = total_score if overall_valid else 0.0
    best_known_lower_bound = max(effective_score, baseline_total_score)
    result = {
        "task_name": prepared["task_name"],
        "valid": overall_valid,
        "score": round(effective_score, 6),
        "baseline_reference_score": round(baseline_total_score, 6),
        "best_known_lower_bound": round(best_known_lower_bound, 6),
        "certified_upper_bound": round(certified_upper_bound, 6),
        "absolute_theoretical_upper_bound": round(absolute_theoretical_upper_bound, 6),
        "gap_to_certified_upper_bound": round(max(0.0, certified_upper_bound - effective_score), 6),
        "relative_gap_to_certified_upper_bound": round(max(0.0, certified_upper_bound - effective_score) / certified_upper_bound, 6) if certified_upper_bound > 0 else None,
        "molecule_results": molecule_results,
    }
    dump_json(result_output_path, result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare and evaluate Task 02.")
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
