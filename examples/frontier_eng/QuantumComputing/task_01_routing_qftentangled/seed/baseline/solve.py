# EVOLVE-BLOCK-START
from __future__ import annotations

from qiskit import transpile
from qiskit.circuit import QuantumCircuit
from qiskit.transpiler import Target

from structural_optimizer import optimize_by_local_rewrite


def _cost(qc: QuantumCircuit) -> float:
    return sum(inst.operation.num_qubits == 2 for inst in qc.data) + 0.2 * qc.depth()


def optimize_circuit(input_circuit: QuantumCircuit, target: Target, case: dict) -> QuantumCircuit:
    """Target-aware transpile search baseline for routing-heavy circuits."""
    qc = optimize_by_local_rewrite(input_circuit)
    if target is None:
        return qc

    num_qubits = case.get("num_qubits", input_circuit.num_qubits)
    best = qc
    best_score = _cost(qc)
    option_sets = (
        {"optimization_level": 3, "layout_method": "sabre", "routing_method": "sabre"},
        {"optimization_level": 3, "layout_method": "lookahead", "routing_method": "sabre"},
        {"optimization_level": 3, "layout_method": "dense", "routing_method": "sabre"},
        {"optimization_level": 3},
        {"optimization_level": 2},
    )
    for seed in (num_qubits + 5, num_qubits + 11, num_qubits + 17, num_qubits + 29):
        for transpile_kwargs in option_sets:
            try:
                candidate = transpile(qc, target=target, seed_transpiler=seed, **transpile_kwargs)
            except Exception:
                continue
            score = _cost(candidate)
            if score < best_score:
                best = candidate
                best_score = score
    return best
# EVOLVE-BLOCK-END
