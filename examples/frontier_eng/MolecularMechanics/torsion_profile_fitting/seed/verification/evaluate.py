from __future__ import annotations

import argparse
import json
import math
import random
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


def _generate_public_samples(tunable_terms: list[str], scale_bounds: dict[str, list[float]], num_public_samples: int, seed: int) -> list[dict[str, float]]:
    rng = random.Random(seed)
    seen = set()
    samples: list[dict[str, float]] = []

    def add_sample(term_scales: dict[str, float]) -> None:
        key = tuple(round(float(term_scales[term_name]), 8) for term_name in tunable_terms)
        if key in seen:
            return
        seen.add(key)
        samples.append({term_name: round(float(term_scales[term_name]), 6) for term_name in tunable_terms})

    add_sample({term_name: 1.0 for term_name in tunable_terms})
    for corner_bits in range(1 << len(tunable_terms)):
        term_scales = {}
        for index, term_name in enumerate(tunable_terms):
            low, high = scale_bounds[term_name]
            term_scales[term_name] = high if ((corner_bits >> index) & 1) else low
        add_sample(term_scales)

    while len(samples) < num_public_samples:
        term_scales = {}
        for term_name in tunable_terms:
            low, high = scale_bounds[term_name]
            term_scales[term_name] = rng.uniform(low, high)
        add_sample(term_scales)

    return samples[:num_public_samples]


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
        from openff.units.openmm import to_openmm
        from rdkit.Chem import rdMolTransforms
    except Exception as exc:
        raise RuntimeError(
            "Task 03 requires an environment with openff-toolkit, openff-units, rdkit, openmm, and numpy."
        ) from exc
    finally:
        metadata.version = original_version

    return {
        "ForceField": ForceField,
        "Molecule": Molecule,
        "np": np,
        "openmm": openmm,
        "openmm_unit": openmm_unit,
        "rdMolTransforms": rdMolTransforms,
        "to_openmm": to_openmm,
        "unit": unit,
    }


def _get_parameter_assignment(force_field, molecule, torsion_atom_indices: tuple[int, int, int, int]):
    labels = force_field.label_molecules(molecule.to_topology())[0]
    assignments = labels.get("ProperTorsions", {})
    assignment = assignments.get(torsion_atom_indices)
    if assignment is None:
        assignment = assignments.get(tuple(reversed(torsion_atom_indices)))
    if assignment is None:
        raise ValueError(f"Could not find a ProperTorsions assignment for torsion {torsion_atom_indices}.")
    return assignment


def _get_parameter_by_id(force_field, parameter_id: str):
    handler = force_field.get_parameter_handler("ProperTorsions")
    matches = handler.get_parameter({"id": parameter_id})
    if not matches:
        raise ValueError(f"Could not find ProperTorsions parameter id {parameter_id!r}.")
    return matches[0]


def _generate_scan_coordinates(molecule, torsion_atom_indices: tuple[int, int, int, int], angles_degrees: list[float], np, rdMolTransforms, unit):
    if molecule.n_conformers == 0:
        molecule.generate_conformers(n_conformers=1)

    rdkit_molecule = molecule.to_rdkit()
    conformer = rdkit_molecule.GetConformer(0)
    scan_coordinates = []
    for angle in angles_degrees:
        rdMolTransforms.SetDihedralDeg(conformer, *torsion_atom_indices, float(angle))
        coordinates = []
        for atom_index in range(rdkit_molecule.GetNumAtoms()):
            position = conformer.GetAtomPosition(atom_index)
            coordinates.append([position.x, position.y, position.z])
        scan_coordinates.append((np.asarray(coordinates) * unit.angstrom).to(unit.angstrom))
    return scan_coordinates


def _build_simulation(force_field, molecule, openmm, openmm_unit):
    topology = molecule.to_topology()
    system = force_field.create_openmm_system(topology, charge_from_molecules=[molecule])
    integrator = openmm.VerletIntegrator(1.0 * openmm_unit.femtoseconds)
    platform = openmm.Platform.getPlatformByName("Reference")
    return openmm.app.Simulation(topology.to_openmm(), system, integrator, platform)


def _relative_profile_from_positions(force_field, molecule, scan_coordinates, openmm, openmm_unit, to_openmm):
    simulation = _build_simulation(force_field, molecule, openmm, openmm_unit)
    absolute_energies = []
    for coordinates in scan_coordinates:
        simulation.context.setPositions(to_openmm(coordinates))
        state = simulation.context.getState(getEnergy=True)
        absolute_energies.append(float(state.getPotentialEnergy().value_in_unit(openmm_unit.kilocalorie_per_mole)))
    minimum = min(absolute_energies)
    return [round(energy - minimum, 6) for energy in absolute_energies]


def _scaled_profile(force_field_name: str, parameter_id: str, base_scales: dict[str, float], term_scales: dict[str, float], molecule, scan_coordinates, tunable_terms: list[str], ForceField, openmm, openmm_unit, to_openmm):
    force_field = ForceField(force_field_name)
    parameter = _get_parameter_by_id(force_field, parameter_id)
    for term_name in tunable_terms:
        current_value = getattr(parameter, term_name)
        base_scale = float(base_scales[term_name])
        target_scale = float(term_scales[term_name])
        setattr(parameter, term_name, current_value * (target_scale / base_scale))
    return _relative_profile_from_positions(force_field, molecule, scan_coordinates, openmm, openmm_unit, to_openmm)


def prepare(raw_task_path: str, prepared_output_path: str) -> None:
    raw = load_json(raw_task_path)
    chem = _import_chemistry_stack()

    ForceField = chem["ForceField"]
    Molecule = chem["Molecule"]
    np = chem["np"]
    openmm = chem["openmm"]
    openmm_unit = chem["openmm_unit"]
    rdMolTransforms = chem["rdMolTransforms"]
    to_openmm = chem["to_openmm"]
    unit = chem["unit"]

    molecule = Molecule.from_smiles(raw["molecule"]["smiles"], allow_undefined_stereo=raw["molecule"].get("allow_undefined_stereo", False))
    molecule.name = raw["molecule"].get("name", raw["molecule"]["smiles"])
    molecule.generate_conformers(n_conformers=1)
    molecule.assign_partial_charges(partial_charge_method="gasteiger")

    torsion_atom_indices = tuple(int(value) for value in raw["torsion_atom_indices"])
    angles_degrees = [float(value) for value in raw["angles_degrees"]]
    tunable_terms = list(raw["tunable_terms"])

    base_force_field = ForceField(raw["force_field"])
    matched_parameter = _get_parameter_assignment(base_force_field, molecule, torsion_atom_indices)
    parameter_id = matched_parameter.id
    base_parameter = _get_parameter_by_id(base_force_field, parameter_id)
    base_term_scales = {term_name: 1.0 for term_name in tunable_terms}
    base_term_values = {
        term_name: round(float(getattr(base_parameter, term_name).m_as(unit.kilocalorie / unit.mole)), 6)
        for term_name in tunable_terms
    }

    scan_coordinates = _generate_scan_coordinates(molecule, torsion_atom_indices, angles_degrees, np, rdMolTransforms, unit)

    scale_bounds = {
        term_name: [float(value) for value in raw["scale_bounds"][term_name]]
        for term_name in tunable_terms
    }
    public_samples = _generate_public_samples(
        tunable_terms,
        scale_bounds,
        int(raw["num_public_samples"]),
        int(raw.get("sampling_seed", 0)),
    )

    candidate_profiles = []
    for candidate_index, term_scales in enumerate(public_samples):
        profile = _scaled_profile(
            raw["force_field"],
            parameter_id,
            base_term_scales,
            term_scales,
            molecule,
            scan_coordinates,
            tunable_terms,
            ForceField,
            openmm,
            openmm_unit,
            to_openmm,
        )
        candidate_profiles.append(
            {
                "candidate_id": f"sample_{candidate_index:04d}",
                "term_scales": term_scales,
                "relative_energies_kcal_per_mol": profile,
            }
        )

    prepared = {
        "task_name": raw["task_name"],
        "angles_degrees": angles_degrees,
        "tunable_terms": tunable_terms,
        "term_scale_bounds": scale_bounds,
        "score_penalty_per_rmse": float(raw.get("score_penalty_per_rmse", 250.0)),
        "target_relative_energies_kcal_per_mol": [float(value) for value in raw["target_relative_energies_kcal_per_mol"]],
        "candidate_profiles": candidate_profiles,
        "metadata": {
            "force_field": raw["force_field"],
            "molecule_name": molecule.name,
            "molecule_smiles": raw["molecule"]["smiles"],
            "torsion_atom_indices": list(torsion_atom_indices),
            "matched_parameter_id": parameter_id,
            "base_term_values_kcal_per_mol": base_term_values,
            "scan_coordinates_angstrom": [coordinates.m_as(unit.angstrom).tolist() for coordinates in scan_coordinates],
            "charge_method": "gasteiger",
            "num_public_samples": int(raw["num_public_samples"]),
            "sampling_seed": int(raw.get("sampling_seed", 0)),
            "known_optimal_score": float(raw.get("known_optimal_score", 100.0)),
            "score_penalty_per_rmse": float(raw.get("score_penalty_per_rmse", 250.0)),
        },
    }
    dump_json(prepared_output_path, prepared)


def evaluate(prepared_input_path: str, solution_path: str, result_output_path: str) -> None:
    prepared = load_json(prepared_input_path)
    solution = load_json(solution_path)
    chem = _import_chemistry_stack()

    ForceField = chem["ForceField"]
    Molecule = chem["Molecule"]
    np = chem["np"]
    openmm = chem["openmm"]
    openmm_unit = chem["openmm_unit"]
    to_openmm = chem["to_openmm"]
    unit = chem["unit"]

    tunable_terms = list(prepared["tunable_terms"])
    score_penalty_per_rmse = float(prepared.get("score_penalty_per_rmse", prepared["metadata"].get("score_penalty_per_rmse", 250.0)))
    term_scale_bounds = {
        term_name: [float(value) for value in prepared["term_scale_bounds"][term_name]]
        for term_name in tunable_terms
    }
    submitted_scales = solution.get("term_scales", {})

    missing_terms = [term_name for term_name in tunable_terms if term_name not in submitted_scales]
    invalid_terms = [term_name for term_name in submitted_scales if term_name not in tunable_terms]
    out_of_bounds_terms = []
    if (not missing_terms) and (not invalid_terms):
        for term_name in tunable_terms:
            low, high = term_scale_bounds[term_name]
            value = float(submitted_scales[term_name])
            if value < low or value > high:
                out_of_bounds_terms.append(term_name)
    valid = (not missing_terms) and (not invalid_terms) and (not out_of_bounds_terms)

    if valid:
        term_scales = {term_name: float(submitted_scales[term_name]) for term_name in tunable_terms}
        molecule = Molecule.from_smiles(prepared["metadata"]["molecule_smiles"], allow_undefined_stereo=True)
        molecule.generate_conformers(n_conformers=1)
        molecule.assign_partial_charges(partial_charge_method="gasteiger")
        scan_coordinates = [
            np.asarray(coordinates) * unit.angstrom
            for coordinates in prepared["metadata"]["scan_coordinates_angstrom"]
        ]
        profile = _scaled_profile(
            prepared["metadata"]["force_field"],
            prepared["metadata"]["matched_parameter_id"],
            {term_name: 1.0 for term_name in tunable_terms},
            term_scales,
            molecule,
            scan_coordinates,
            tunable_terms,
            ForceField,
            openmm,
            openmm_unit,
            to_openmm,
        )
        target_profile = [float(value) for value in prepared["target_relative_energies_kcal_per_mol"]]
        profile_rmse = rmse(profile, target_profile)
        score = score_from_rmse(profile_rmse, score_penalty_per_rmse)
    else:
        term_scales = {}
        profile = []
        profile_rmse = float("inf")
        score = 0.0

    public_sample_best_score = 0.0
    public_sample_best_candidate_id = None
    for candidate in prepared["candidate_profiles"]:
        candidate_score = score_from_rmse(
            rmse(
                [float(value) for value in candidate["relative_energies_kcal_per_mol"]],
                [float(value) for value in prepared["target_relative_energies_kcal_per_mol"]],
            ),
            score_penalty_per_rmse,
        )
        if candidate_score > public_sample_best_score:
            public_sample_best_score = candidate_score
            public_sample_best_candidate_id = candidate["candidate_id"]

    known_optimal_score = float(prepared["metadata"].get("known_optimal_score", 100.0))

    result = {
        "task_name": prepared["task_name"],
        "valid": valid,
        "missing_terms": missing_terms,
        "invalid_terms": invalid_terms,
        "out_of_bounds_terms": out_of_bounds_terms,
        "submitted_term_scales": term_scales,
        "predicted_relative_energies_kcal_per_mol": profile,
        "target_relative_energies_kcal_per_mol": prepared["target_relative_energies_kcal_per_mol"],
        "rmse_kcal_per_mol": round(profile_rmse, 6) if math.isfinite(profile_rmse) else None,
        "score": round(score, 6),
        "public_sample_best_score": round(public_sample_best_score, 6),
        "public_sample_best_candidate_id": public_sample_best_candidate_id,
        "known_optimal_score": round(known_optimal_score, 6),
        "gap_to_known_optimal": round(max(0.0, known_optimal_score - score), 6),
        "relative_gap_to_known_optimal": round(max(0.0, known_optimal_score - score) / known_optimal_score, 6) if known_optimal_score > 0 else None,
        "score_penalty_per_rmse": round(score_penalty_per_rmse, 6),
    }
    dump_json(result_output_path, result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare and evaluate Task 03.")
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
