"""Baseline solution for the Antibiotic Drug Design task.

Generates SMILES molecules optimized for K. pneumoniae antibacterial activity.
Uses random molecular perturbation with RDKit as a starting point.

Must define run() -> list[str] returning SMILES strings.
"""

import os
import random

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors, QED

    HAS_RDKIT = True
except ImportError:
    HAS_RDKIT = False

NUM_MOLECULES = 100
NUM_GENERATIONS = 3
POPULATION_SIZE = 60


def load_starter_molecules() -> list[str]:
    """Load starter molecules from data/starter_molecules.smi."""
    smi_path = os.path.join(os.path.dirname(__file__), "data", "starter_molecules.smi")
    molecules = []
    if os.path.exists(smi_path):
        with open(smi_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    smiles = line.split()[0]
                    molecules.append(smiles)
    return molecules


def is_valid_smiles(smiles: str) -> bool:
    """Check if a SMILES string is valid."""
    if not HAS_RDKIT:
        return len(smiles) > 0
    mol = Chem.MolFromSmiles(smiles)
    return mol is not None


def mutate_smiles(smiles: str) -> str:
    """Apply a random mutation to a SMILES molecule."""
    if not HAS_RDKIT:
        return smiles

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return smiles

    # Try random atom replacement
    try:
        rw_mol = Chem.RWMol(mol)
        atoms = list(range(rw_mol.GetNumAtoms()))
        if not atoms:
            return smiles

        idx = random.choice(atoms)
        replacements = [6, 7, 8, 9, 16, 17]  # C, N, O, F, S, Cl
        rw_mol.GetAtomWithIdx(idx).SetAtomicNum(random.choice(replacements))

        Chem.SanitizeMol(rw_mol)
        new_smiles = Chem.MolToSmiles(rw_mol)
        if Chem.MolFromSmiles(new_smiles) is not None:
            return new_smiles
    except Exception:
        pass

    return smiles


def compute_qed(smiles: str) -> float:
    """Compute QED drug-likeness score."""
    if not HAS_RDKIT:
        return 0.5
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return 0.0
    try:
        return QED.qed(mol)
    except Exception:
        return 0.0


def run() -> list[str]:
    """Generate candidate antibiotic molecules.

    Returns:
        List of SMILES strings representing drug candidates.
    """
    # Load starters
    starters = load_starter_molecules()
    if not starters:
        # Fallback: simple drug-like SMILES
        starters = [
            "c1ccccc1C(=O)O",
            "CC(=O)Nc1ccccc1",
            "Oc1ccc(cc1)C(=O)O",
            "c1ccncc1C(=O)N",
            "CC(=O)c1ccc(N)cc1",
        ]

    # Filter to valid SMILES
    population = [s for s in starters if is_valid_smiles(s)]

    # Expand population with mutations
    max_attempts = POPULATION_SIZE * 20
    attempts = 0
    while len(population) < POPULATION_SIZE and attempts < max_attempts:
        parent = random.choice(starters)
        mutant = mutate_smiles(parent)
        if is_valid_smiles(mutant) and mutant not in population:
            population.append(mutant)
        attempts += 1

    # Evolutionary optimization using QED as proxy fitness
    for gen in range(NUM_GENERATIONS):
        # Score by QED
        scored = [(compute_qed(s), s) for s in population]
        scored.sort(key=lambda x: x[0], reverse=True)

        # Select top half
        survivors = [s for _, s in scored[: POPULATION_SIZE // 2]]

        # Generate offspring via mutation
        offspring = []
        attempts = 0
        while len(offspring) < POPULATION_SIZE // 2 and attempts < 500:
            parent = random.choice(survivors)
            child = mutate_smiles(parent)
            if is_valid_smiles(child):
                offspring.append(child)
            attempts += 1

        population = survivors + offspring

    # Deduplicate and return top molecules by QED
    seen = set()
    unique = []
    for s in population:
        canonical = s
        if HAS_RDKIT:
            mol = Chem.MolFromSmiles(s)
            if mol:
                canonical = Chem.MolToSmiles(mol)
        if canonical not in seen:
            seen.add(canonical)
            unique.append(canonical)

    scored = [(compute_qed(s), s) for s in unique]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:NUM_MOLECULES]]
