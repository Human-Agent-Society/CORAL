from __future__ import annotations

import importlib.util
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


def _find_repo_root(start_dir: Path) -> Path:
    for candidate in (start_dir, *start_dir.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "src").exists():
            return candidate
    msg = f"Could not locate repository root from {start_dir}."
    raise FileNotFoundError(msg)

from qiskit.circuit import QuantumCircuit
from qiskit.qasm2 import dump as dump_qasm2


@dataclass(frozen=True)
class CircuitMetrics:
    depth: int
    size: int
    two_qubit_count: int
    cx_count: int
    ecr_count: int
    swap_count: int
    t_count: int
    tdg_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_metrics(qc: QuantumCircuit) -> CircuitMetrics:
    ops = qc.count_ops()
    two_qubit_gate_names = {"cx", "cz", "ecr", "swap", "rzz", "zz", "ms"}
    two_qubit_count = sum(int(count) for gate, count in ops.items() if gate.lower() in two_qubit_gate_names)
    return CircuitMetrics(
        depth=qc.depth(),
        size=qc.size(),
        two_qubit_count=two_qubit_count,
        cx_count=int(ops.get("cx", 0)),
        ecr_count=int(ops.get("ecr", 0)),
        swap_count=int(ops.get("swap", 0)),
        t_count=int(ops.get("t", 0)),
        tdg_count=int(ops.get("tdg", 0)),
    )


def timed_call(func: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[Any, float]:
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return result, elapsed


def load_cases(task_dir: Path) -> list[dict[str, Any]]:
    tests_dir = task_dir / "tests"
    case_paths = sorted(tests_dir.glob("case_*.json"))
    if not case_paths:
        raise FileNotFoundError(f"No test case files found in {tests_dir}.")
    return [json.loads(path.read_text(encoding="utf-8")) for path in case_paths]


def load_solver(task_dir: Path) -> Callable[..., QuantumCircuit]:
    solve_path = task_dir / "baseline" / "solve.py"
    if not solve_path.exists():
        raise FileNotFoundError(f"Missing solver file: {solve_path}")

    solver_dir = solve_path.parent
    if str(solver_dir) not in sys.path:
        sys.path.insert(0, str(solver_dir))

    module_name = f"{task_dir.name}_solve"
    spec = importlib.util.spec_from_file_location(module_name, solve_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to import solver from {solve_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    optimize_circuit = getattr(module, "optimize_circuit", None)
    if not callable(optimize_circuit):
        msg = f"{solve_path} must define callable `optimize_circuit(input_circuit, target, case)`."
        raise AttributeError(msg)

    return optimize_circuit


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def create_run_dir(task_dir: Path, prefix: str = "run") -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = task_dir / "runs" / f"{prefix}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def save_circuit_qasm(qc: QuantumCircuit, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8") as handle:
            dump_qasm2(qc, handle)
    except Exception as exc:
        path.with_suffix(".qasm_error.txt").write_text(
            f"Failed to export QASM2: {exc}\n",
            encoding="utf-8",
        )


def save_circuit_image(
    qc: QuantumCircuit,
    path: Path,
    *,
    max_qubits: int = 40,
    max_size: int = 4000,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if qc.num_qubits > max_qubits or qc.size() > max_size:
        note = (
            f"Skipped PNG rendering (num_qubits={qc.num_qubits}, size={qc.size()}) "
            f"because it exceeds limits max_qubits={max_qubits}, max_size={max_size}.\n"
        )
        path.with_suffix(".image_skipped.txt").write_text(note, encoding="utf-8")
        return

    try:
        import matplotlib.pyplot as plt  # noqa: PLC0415
    except Exception as exc:
        path.with_suffix(".image_error.txt").write_text(
            f"Failed to import matplotlib for circuit drawing: {exc}\n",
            encoding="utf-8",
        )
        return

    try:
        figure = qc.draw(output="mpl", fold=-1, idle_wires=False)
        figure.savefig(path, dpi=180, bbox_inches="tight")
        plt.close(figure)
    except Exception as exc:
        path.with_suffix(".image_error.txt").write_text(
            f"Failed to render circuit image: {exc}\n",
            encoding="utf-8",
        )


def save_circuit_artifacts(
    qc: QuantumCircuit,
    output_dir: Path,
    stem: str,
    *,
    save_image: bool = True,
    max_qubits_for_image: int = 40,
    max_size_for_image: int = 4000,
) -> None:
    save_circuit_qasm(qc, output_dir / f"{stem}.qasm")
    if save_image:
        save_circuit_image(
            qc,
            output_dir / f"{stem}.png",
            max_qubits=max_qubits_for_image,
            max_size=max_size_for_image,
        )
