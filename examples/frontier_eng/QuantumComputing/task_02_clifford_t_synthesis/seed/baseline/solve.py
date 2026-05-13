# EVOLVE-BLOCK-START
from __future__ import annotations

from qiskit import transpile
from qiskit.circuit import QuantumCircuit
from qiskit.transpiler import Target

from structural_optimizer import optimize_by_local_rewrite


def optimize_circuit(input_circuit: QuantumCircuit, target: Target, case: dict) -> QuantumCircuit:
    """Baseline that combines local rewrites with aggressive phase-aware transpilation."""
    _ = (target, case)

    optimized = optimize_by_local_rewrite(input_circuit, max_rounds=20)
    # Keep the synthesized circuit inside the evaluator's advertised Clifford+T basis.
    basis_gates = ["cx", "h", "x", "y", "z", "s", "sdg", "t", "tdg"]
    transpiled = transpile(
        optimized,
        basis_gates=basis_gates,
        optimization_level=3,
        seed_transpiler=42,
    )
    return optimize_by_local_rewrite(transpiled, max_rounds=20)
# EVOLVE-BLOCK-END
