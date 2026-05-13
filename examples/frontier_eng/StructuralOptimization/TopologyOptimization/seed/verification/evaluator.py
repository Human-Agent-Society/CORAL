"""Evaluator for Topology Optimization — MBB Beam (SIMP Method)"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

INVALID_COMBINED_SCORE = -1e18


def _find_repo_root(start: Path | None = None) -> Path:
    """Locate the repository root directory."""
    if "FRONTIER_ENGINEERING_ROOT" in os.environ:
        return Path(os.environ["FRONTIER_ENGINEERING_ROOT"]).expanduser().resolve()
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / "frontier_eval").is_dir() and (parent / "benchmarks").is_dir():
            return parent
    return Path.cwd().resolve()


def _tail(text: str, limit: int = 8000) -> str:
    return text if len(text) <= limit else text[-limit:]


def _truncate_middle(text: str, limit: int = 200_000) -> str:
    if len(text) <= limit:
        return text
    keep = max(0, (limit - 128) // 2)
    omitted = len(text) - 2 * keep
    return text[:keep] + f"\n\n[... truncated {omitted} chars ...]\n\n" + text[-keep:]


def load_problem_config(repo_root: Path) -> dict:
    """Load the problem configuration JSON."""
    candidates = [
        repo_root / "benchmarks" / "StructuralOptimization" / "TopologyOptimization"
        / "references" / "problem_config.json",
        repo_root / "StructuralOptimization" / "TopologyOptimization"
        / "references" / "problem_config.json",
    ]
    for path in candidates:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(
        f"problem_config.json not found. Searched: {[str(p) for p in candidates]}"
    )


# ============================================================================
# Independent FEM solver (mirrors init.py exactly)
# ============================================================================

def _element_stiffness_matrix(nu: float) -> np.ndarray:
    """8x8 element stiffness matrix for unit-size Q4 element, plane stress."""
    k = np.array([
        1/2 - nu/6, 1/8 + nu/8, -1/4 - nu/12, -1/8 + 3*nu/8,
        -1/4 + nu/12, -1/8 - nu/8, nu/6, 1/8 - 3*nu/8
    ])
    KE = (1.0 / (1.0 - nu**2)) * np.array([
        [k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7]],
        [k[1], k[0], k[7], k[6], k[5], k[4], k[3], k[2]],
        [k[2], k[7], k[0], k[5], k[6], k[3], k[4], k[1]],
        [k[3], k[6], k[5], k[0], k[7], k[2], k[1], k[4]],
        [k[4], k[5], k[6], k[7], k[0], k[1], k[2], k[3]],
        [k[5], k[4], k[3], k[2], k[1], k[0], k[7], k[6]],
        [k[6], k[3], k[4], k[1], k[2], k[7], k[0], k[5]],
        [k[7], k[2], k[1], k[4], k[3], k[6], k[5], k[0]],
    ])
    return KE


def _fem_solve(nelx: int, nely: int, density: np.ndarray, config: dict) -> np.ndarray:
    """Solve the 2D FEM problem with Q4 elements. Returns displacement vector."""
    E0 = config["E0"]
    Emin = config["Emin"]
    nu = config["nu"]
    penal = config["penal"]

    KE = _element_stiffness_matrix(nu)
    n_dofs = 2 * (nelx + 1) * (nely + 1)

    iK = np.zeros(64 * nelx * nely, dtype=int)
    jK = np.zeros(64 * nelx * nely, dtype=int)
    sK = np.zeros(64 * nelx * nely, dtype=float)

    for elx in range(nelx):
        for ely in range(nely):
            e_idx = elx * nely + ely
            n1 = elx * (nely + 1) + ely
            n2 = (elx + 1) * (nely + 1) + ely
            edof = np.array([
                2*n1, 2*n1+1,
                2*n2, 2*n2+1,
                2*n2+2, 2*n2+3,
                2*n1+2, 2*n1+3,
            ])
            Ee = Emin + density[ely, elx]**penal * (E0 - Emin)
            for i_local in range(8):
                for j_local in range(8):
                    idx = e_idx * 64 + i_local * 8 + j_local
                    iK[idx] = edof[i_local]
                    jK[idx] = edof[j_local]
                    sK[idx] = Ee * KE[i_local, j_local]

    K = coo_matrix((sK, (iK, jK)), shape=(n_dofs, n_dofs)).tocsc()

    F = np.zeros(n_dofs)
    F[1] = config["force"]["fy"]

    fixed_dofs = []
    for i in range(nely + 1):
        fixed_dofs.append(2 * i)
    fixed_dofs.append(2 * (nelx * (nely + 1) + nely) + 1)

    fixed_dofs = np.array(fixed_dofs, dtype=int)
    all_dofs = np.arange(n_dofs)
    free_dofs = np.setdiff1d(all_dofs, fixed_dofs)

    K_ff = K[free_dofs, :][:, free_dofs]
    F_f = F[free_dofs]

    u = np.zeros(n_dofs)
    u[free_dofs] = spsolve(K_ff, F_f)

    return u


def _compute_compliance(
    nelx: int, nely: int, density: np.ndarray, u: np.ndarray, config: dict
) -> float:
    """Compute total compliance c = F^T u via element summation."""
    E0 = config["E0"]
    Emin = config["Emin"]
    nu = config["nu"]
    penal = config["penal"]

    KE = _element_stiffness_matrix(nu)

    compliance = 0.0
    for elx in range(nelx):
        for ely in range(nely):
            n1 = elx * (nely + 1) + ely
            n2 = (elx + 1) * (nely + 1) + ely
            edof = np.array([
                2*n1, 2*n1+1,
                2*n2, 2*n2+1,
                2*n2+2, 2*n2+3,
                2*n1+2, 2*n1+3,
            ])
            ue = u[edof]
            Ee = Emin + density[ely, elx]**penal * (E0 - Emin)
            compliance += Ee * float(ue @ KE @ ue)

    return compliance


def evaluate_topology(
    density_vector: list[float], config: dict
) -> dict[str, Any]:
    """
    Evaluate a topology optimization solution.

    Parameters
    ----------
    density_vector : list of float
        Flattened density field of length nelx * nely.
    config : dict
        Problem configuration.

    Returns
    -------
    result : dict
        Evaluation results including compliance, volume fraction, feasibility.
    """
    nelx = config["nelx"]
    nely = config["nely"]
    volfrac = config["volfrac"]
    rho_min = 1e-3

    expected_len = nelx * nely
    x = np.array(density_vector, dtype=float)

    # --- Input validation ---
    if len(x) != expected_len:
        return {
            "compliance": float("inf"),
            "volume_fraction": 0.0,
            "feasible": False,
            "error": f"Expected {expected_len} elements, got {len(x)}",
        }

    if not np.all(np.isfinite(x)):
        return {
            "compliance": float("inf"),
            "volume_fraction": 0.0,
            "feasible": False,
            "error": "Density vector contains NaN or Inf values",
        }

    # Clip densities to valid range
    x = np.clip(x, rho_min, 1.0)
    density = x.reshape((nely, nelx))

    # --- FEM solve ---
    try:
        u = _fem_solve(nelx, nely, density, config)
    except Exception as exc:
        return {
            "compliance": float("inf"),
            "volume_fraction": float(np.mean(density)),
            "feasible": False,
            "error": f"FEM solve failed: {exc}",
        }

    # --- Compute compliance ---
    try:
        compliance = _compute_compliance(nelx, nely, density, u, config)
    except Exception as exc:
        return {
            "compliance": float("inf"),
            "volume_fraction": float(np.mean(density)),
            "feasible": False,
            "error": f"Compliance computation failed: {exc}",
        }

    vol_frac = float(np.mean(density))

    # Volume fraction constraint: Σρ / N ≤ volfrac (with tolerance)
    feasible = vol_frac <= volfrac + 1e-6

    return {
        "compliance": float(compliance),
        "volume_fraction": vol_frac,
        "feasible": bool(feasible),
    }


def evaluate(program_path: str, *, repo_root: Path | None = None) -> Any:
    """
    Full evaluation pipeline:
    1. Run candidate program to produce submission.json
    2. Parse and validate submission
    3. Run independent FEM + constraint check
    4. Return metrics

    Parameters
    ----------
    program_path : str
        Path to the candidate Python program.
    repo_root : Path, optional
        Repository root. Auto-detected if not given.
    """
    start = time.time()
    repo_root = (
        _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    )
    program_path_resolved = str(Path(program_path).expanduser().resolve())

    work_dir = Path(tempfile.mkdtemp(prefix="fe_topology_")).resolve()
    artifacts: dict[str, str] = {}

    metrics: dict[str, float] = {
        "combined_score": INVALID_COMBINED_SCORE,
        "compliance": 0.0,
        "volume_fraction": 0.0,
        "valid": 0.0,
        "feasible": 0.0,
        "timeout": 0.0,
        "runtime_s": 0.0,
    }

    try:
        # 1. Copy problem config to work dir for the solver to access
        config = load_problem_config(repo_root)
        refs_dir = work_dir / "references"
        refs_dir.mkdir(parents=True, exist_ok=True)
        with open(refs_dir / "problem_config.json", "w", encoding="utf-8") as f:
            json.dump(config, f)

        # 2. Run candidate program
        try:
            proc = subprocess.run(
                [sys.executable, program_path_resolved],
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=600,
            )
        except subprocess.TimeoutExpired as e:
            metrics["timeout"] = 1.0
            metrics["runtime_s"] = float(time.time() - start)
            artifacts["error_message"] = f"program timeout: {e}"
            return _wrap(metrics, artifacts)

        artifacts["program_stdout"] = _tail(proc.stdout)
        artifacts["program_stderr"] = _tail(proc.stderr)
        artifacts["program_stdout_full"] = _truncate_middle(proc.stdout)
        artifacts["program_stderr_full"] = _truncate_middle(proc.stderr)
        metrics["program_returncode"] = float(proc.returncode)

        # 3. Read submission
        submission_path = work_dir / "temp" / "submission.json"
        if not submission_path.exists():
            submission_path = work_dir / "submission.json"
        if not submission_path.exists():
            artifacts["error_message"] = (
                "submission.json not generated "
                "(checked temp/submission.json and submission.json)"
            )
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        try:
            with open(submission_path, "r", encoding="utf-8") as f:
                submission = json.load(f)
            artifacts["submission.json"] = json.dumps(submission, indent=2)
        except Exception as exc:
            artifacts["error_message"] = f"Failed to parse submission.json: {exc}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        if "density_vector" not in submission:
            artifacts["error_message"] = "submission.json missing 'density_vector'"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        # 4. Evaluate
        result = evaluate_topology(submission["density_vector"], config)
        artifacts["evaluation_result"] = json.dumps(result, indent=2)

        runtime_s = time.time() - start
        metrics["compliance"] = result.get("compliance", 0.0)
        metrics["volume_fraction"] = result.get("volume_fraction", 0.0)
        metrics["runtime_s"] = float(runtime_s)
        metrics["feasible"] = 1.0 if result.get("feasible", False) else 0.0

        if result.get("feasible", False):
            # Minimization: negate compliance so higher combined_score = better
            metrics["combined_score"] = -float(result["compliance"])
            metrics["valid"] = 1.0
        else:
            metrics["combined_score"] = INVALID_COMBINED_SCORE
            metrics["valid"] = 0.0

        return _wrap(metrics, artifacts)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _wrap(metrics: dict[str, float], artifacts: dict[str, str]) -> Any:
    try:
        from openevolve.evaluation_result import EvaluationResult

        return EvaluationResult(metrics=metrics, artifacts=artifacts)
    except Exception:
        return metrics


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python evaluator.py <program_path>")
        sys.exit(1)

    result = evaluate(sys.argv[1])
    if hasattr(result, "metrics"):
        output = {"metrics": result.metrics, "artifacts": result.artifacts}
    else:
        output = result
    print(json.dumps(output, indent=2))
