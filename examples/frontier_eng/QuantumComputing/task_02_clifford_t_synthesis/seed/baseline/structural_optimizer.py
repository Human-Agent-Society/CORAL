from __future__ import annotations

import math
from typing import Any

from qiskit.circuit import QuantumCircuit
from qiskit.circuit.library import CPhaseGate, PhaseGate, RXGate, RYGate, RZGate, RZZGate

_SELF_INVERSE = {"x", "y", "z", "h", "cx", "cz", "swap", "ecr"}
_INVERSE_PAIRS = {
    ("s", "sdg"),
    ("sdg", "s"),
    ("t", "tdg"),
    ("tdg", "t"),
    ("sx", "sxdg"),
    ("sxdg", "sx"),
}
_MERGEABLE_PARAM_GATES = {"rz", "rx", "ry", "p", "cp", "rzz"}
_ANGLE_TOL = 1e-10


def _normalize_angle(theta: float) -> float:
    wrapped = (theta + math.pi) % (2 * math.pi) - math.pi
    if abs(wrapped) < _ANGLE_TOL:
        return 0.0
    return wrapped


def _as_float_if_bound(param: Any) -> float | None:
    try:
        if hasattr(param, "parameters") and len(param.parameters) > 0:
            return None
    except Exception:
        return None
    try:
        return float(param)
    except Exception:
        return None


def _make_param_gate(name: str, theta: float):
    if name == "rz":
        return RZGate(theta)
    if name == "rx":
        return RXGate(theta)
    if name == "ry":
        return RYGate(theta)
    if name == "p":
        return PhaseGate(theta)
    if name == "cp":
        return CPhaseGate(theta)
    if name == "rzz":
        return RZZGate(theta)
    msg = f"Unsupported mergeable gate name: {name}"
    raise ValueError(msg)


def _same_operands(a: tuple[Any, tuple[Any, ...], tuple[Any, ...]], b: tuple[Any, tuple[Any, ...], tuple[Any, ...]]) -> bool:
    return a[1] == b[1] and a[2] == b[2]


def _has_condition(op: Any) -> bool:
    return getattr(op, "condition", None) is not None


def _try_merge_pair(
    first: tuple[Any, tuple[Any, ...], tuple[Any, ...]],
    second: tuple[Any, tuple[Any, ...], tuple[Any, ...]],
) -> tuple[Any, tuple[Any, ...], tuple[Any, ...]] | str | None:
    op_a, qargs_a, cargs_a = first
    op_b, qargs_b, cargs_b = second
    name_a = op_a.name
    name_b = op_b.name

    if _has_condition(op_a) or _has_condition(op_b):
        return None

    if cargs_a or cargs_b:
        return None

    if (name_a == "barrier") or (name_b == "barrier"):
        return None

    if not _same_operands(first, second):
        return None

    if name_a == name_b and name_a in _SELF_INVERSE:
        return "cancel"

    if (name_a, name_b) in _INVERSE_PAIRS:
        return "cancel"

    if name_a == name_b and name_a in _MERGEABLE_PARAM_GATES:
        if len(op_a.params) != 1 or len(op_b.params) != 1:
            return None
        theta_a = _as_float_if_bound(op_a.params[0])
        theta_b = _as_float_if_bound(op_b.params[0])
        if theta_a is None or theta_b is None:
            return None
        theta = _normalize_angle(theta_a + theta_b)
        if theta == 0.0:
            return "cancel"
        return (_make_param_gate(name_a, theta), qargs_a, ())

    return None


def optimize_by_local_rewrite(input_circuit: QuantumCircuit, *, max_rounds: int = 8) -> QuantumCircuit:
    """Perform simple structural rewrites without calling transpile.

    Rewrites include:
    - barrier removal
    - adjacent self-inverse cancellation
    - adjacent inverse-pair cancellation (e.g., S + Sdg)
    - adjacent angle-merge for parameterized rotation gates
    """
    instructions: list[tuple[Any, tuple[Any, ...], tuple[Any, ...]]] = [
        (inst.operation, tuple(inst.qubits), tuple(inst.clbits)) for inst in input_circuit.data
    ]

    for _ in range(max_rounds):
        changed = False
        new_instructions: list[tuple[Any, tuple[Any, ...], tuple[Any, ...]]] = []
        i = 0
        while i < len(instructions):
            op_i, q_i, c_i = instructions[i]
            if op_i.name == "barrier":
                changed = True
                i += 1
                continue

            if i + 1 < len(instructions):
                merged = _try_merge_pair(instructions[i], instructions[i + 1])
                if merged == "cancel":
                    changed = True
                    i += 2
                    continue
                if merged is not None:
                    changed = True
                    new_instructions.append(merged)
                    i += 2
                    continue

            new_instructions.append((op_i, q_i, c_i))
            i += 1

        instructions = new_instructions
        if not changed:
            break

    optimized = QuantumCircuit(*input_circuit.qregs, *input_circuit.cregs, name=f"{input_circuit.name}_structopt")
    for op, qargs, cargs in instructions:
        optimized.append(op, list(qargs), list(cargs))
    return optimized

