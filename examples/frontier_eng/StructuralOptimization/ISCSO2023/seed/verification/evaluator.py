
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

INVALID_COMBINED_SCORE = -1e18


def _find_repo_root(start: Path | None = None) -> Path:
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


def load_problem_data(repo_root: Path) -> dict | None:
    candidates = [
        repo_root / "benchmarks" / "StructuralOptimization" / "ISCSO2023"
        / "references" / "problem_data.json",
        repo_root / "StructuralOptimization" / "ISCSO2023"
        / "references" / "problem_data.json",
    ]
    for path in candidates:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


def load_section_database(repo_root: Path, problem: dict | None = None) -> dict[int, float] | None:
    if problem and "section_database" in problem and "sections" in problem["section_database"]:
        return {s["id"]: s.get("area_mm2", s.get("area_cm2", 0.0) * 100) for s in problem["section_database"]["sections"]}
    candidates = [
        repo_root / "benchmarks" / "StructuralOptimization" / "ISCSO2023"
        / "references" / "section_database.json",
        repo_root / "StructuralOptimization" / "ISCSO2023"
        / "references" / "section_database.json",
    ]
    for path in candidates:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "sections" in data:
                    return {s["id"]: s.get("area_mm2", s.get("area_cm2", 0.0) * 100) for s in data["sections"]}
    return None


def build_fem_and_evaluate(
    solution_vector: list[float], problem: dict, repo_root: Path | None = None
) -> dict[str, Any]:
    fem_dir = Path(__file__).resolve().parent
    if str(fem_dir) not in sys.path:
        sys.path.insert(0, str(fem_dir))
    from fem_truss3d import TrussFEM3D, generate_tower_topology

    x = np.array(solution_vector, dtype=float)
    expected_dim = problem["dimension"]
    if len(x) != expected_dim:
        return {
            "objective": float("inf"),
            "feasible": False,
            "error": f"Expected {expected_dim} variables, got {len(x)}",
            "score": float("inf"),
        }

    if not np.all(np.isfinite(x)):
        return {
            "objective": float("inf"),
            "feasible": False,
            "error": "Solution contains NaN or Inf values",
            "score": float("inf"),
        }

    bounds = problem["variable_bounds"]
    
    if bounds.get("discrete", False):
        if repo_root is None:
            repo_root = _find_repo_root()
        section_db = load_section_database(repo_root, problem)
        if section_db is None or len(section_db) == 0:
            return {
                "objective": float("inf"),
                "feasible": False,
                "error": "Section database not found or empty",
                "score": float("inf"),
            }
        section_ids = np.round(x).astype(int)
        id_min, id_max = bounds["section_id_min"], bounds["section_id_max"]
        
        if np.any(section_ids < id_min) or np.any(section_ids > id_max):
            return {
                "objective": float("inf"),
                "feasible": False,
                "error": f"Section IDs must be in [{id_min}, {id_max}], got range [{section_ids.min()}, {section_ids.max()}]",
                "score": float("inf"),
            }
        
        areas = np.array([section_db.get(sid, 0.0) for sid in section_ids], dtype=float)
        if np.any(areas == 0.0):
            invalid_ids = [sid for sid in section_ids if sid not in section_db]
            return {
                "objective": float("inf"),
                "feasible": False,
                "error": f"Invalid section IDs: {invalid_ids}",
                "score": float("inf"),
            }
    else:
        # Continuous: use areas directly
        areas = x
        a_min, a_max = bounds.get("area_min", 10.0), bounds.get("area_max", 20000.0)
        if np.any(areas < a_min - 1e-9) or np.any(areas > a_max + 1e-9):
            return {
                "objective": float("inf"),
                "feasible": False,
                "error": f"Area variables out of bounds [{a_min}, {a_max}]",
                "score": float("inf"),
            }
        areas = np.clip(areas, a_min, a_max)

    tp = problem["tower_parameters"]
    nodes, elements = generate_tower_topology(
        num_levels=tp["num_levels"],
        total_height=tp["total_height_mm"],
        bottom_half_width=tp["bottom_half_width_mm"],
        top_half_width=tp["top_half_width_mm"],
        cross_bracing_levels=tp["cross_bracing_levels"],
    )

    n_elements = len(elements)
    if n_elements != problem["num_bars"]:
        return {
            "objective": float("inf"),
            "feasible": False,
            "error": (
                f"Topology mismatch: generated {n_elements} bars, "
                f"expected {problem['num_bars']}"
            ),
            "score": float("inf"),
        }

    E = problem["material"]["E"]
    rho = problem["material"]["rho"]
    supports = problem["supports"]
    fem = TrussFEM3D(nodes, elements, E, supports)

    constraints = problem["constraints"]
    sigma_limit = constraints["stress_limit"]
    disp_limit = constraints["displacement_limit"]
    tol = constraints.get("tolerance", 1e-6)

    supported_nodes = {s["node"] for s in problem["supports"]}
    unsupported_nodes = [i for i in range(problem["num_nodes"]) if i not in supported_nodes]
    num_unsupported = len(unsupported_nodes)

    max_stress_vio = 0.0
    max_disp_vio = 0.0

    for lc in problem["load_cases"]:
        force_vec = np.zeros(3 * problem["num_nodes"])
        
        if len(lc.get("loads", [])) == 0:
            if lc["id"] == 0:
                load_per_node = 12000.0 / num_unsupported
                for nid in unsupported_nodes:
                    force_vec[3 * nid] += load_per_node
            elif lc["id"] == 1:
                load_per_node = 12000.0 / num_unsupported
                for nid in unsupported_nodes:
                    force_vec[3 * nid + 1] += load_per_node
            elif lc["id"] == 2:
                load_per_node = 15000.0 / num_unsupported
                for nid in unsupported_nodes:
                    force_vec[3 * nid + 2] -= load_per_node
        else:
            for load in lc["loads"]:
                nid = load["node"]
                force_vec[3 * nid] += load["fx"]
                force_vec[3 * nid + 1] += load["fy"]
                force_vec[3 * nid + 2] += load["fz"]

        displacements, stresses = fem.solve(areas, force_vec)
        abs_stresses = np.abs(stresses)
        stress_violations = abs_stresses - sigma_limit
        lc_max_stress_vio = float(np.max(stress_violations))
        max_stress_vio = max(max_stress_vio, lc_max_stress_vio)

        abs_disp = np.abs(displacements)
        disp_violations = abs_disp - disp_limit
        lc_max_disp_vio = float(np.max(disp_violations))
        max_disp_vio = max(max_disp_vio, lc_max_disp_vio)

    weight = fem.compute_weight(areas, rho)
    feasible = (max_stress_vio <= tol) and (max_disp_vio <= tol)

    return {
        "objective": float(weight),
        "feasible": bool(feasible),
        "max_stress_violation": float(max(max_stress_vio, 0.0)),
        "max_displacement_violation": float(max(max_disp_vio, 0.0)),
        "score": float(weight) if feasible else float("inf"),
        "num_load_cases": len(problem["load_cases"]),
    }


def evaluate(program_path: str, *, repo_root: Path | None = None, algorithm_config: dict | None = None) -> Any:
    start = time.time()
    repo_root = (
        _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    )
    program_path_resolved = str(Path(program_path).expanduser().resolve())

    work_dir = Path(tempfile.mkdtemp(prefix="fe_iscso2023_")).resolve()
    artifacts: dict[str, str] = {}

    metrics: dict[str, float] = {
        "combined_score": INVALID_COMBINED_SCORE,
        "weight_kg": 0.0,
        "valid": 0.0,
        "feasible": 0.0,
        "timeout": 0.0,
        "runtime_s": 0.0,
    }

    problem = load_problem_data(repo_root)
    if problem is None:
        metrics["runtime_s"] = float(time.time() - start)
        metrics["combined_score"] = INVALID_COMBINED_SCORE
        metrics["valid"] = 0.0
        artifacts["error_message"] = "problem_data.json not found"
        shutil.rmtree(work_dir, ignore_errors=True)
        return _wrap(metrics, artifacts)

    refs_dir = work_dir / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)
    with open(refs_dir / "problem_data.json", "w", encoding="utf-8") as f:
        json.dump(problem, f)

    timeout = 1200
    if algorithm_config and "timeout" in algorithm_config:
        timeout = algorithm_config["timeout"]
    
    proc = subprocess.run(
        [sys.executable, program_path_resolved],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if proc.returncode != 0 or proc.stderr:
        metrics["timeout"] = 1.0 if proc.returncode == -1 else 0.0
        metrics["runtime_s"] = float(time.time() - start)
        metrics["combined_score"] = INVALID_COMBINED_SCORE
        metrics["valid"] = 0.0
        artifacts["error_message"] = f"program failed with return code {proc.returncode}"
        artifacts["program_stderr"] = _tail(proc.stderr)
        shutil.rmtree(work_dir, ignore_errors=True)
        return _wrap(metrics, artifacts)

    artifacts["program_stdout"] = _tail(proc.stdout)
    artifacts["program_stderr"] = _tail(proc.stderr)
    artifacts["program_stdout_full"] = _truncate_middle(proc.stdout)
    artifacts["program_stderr_full"] = _truncate_middle(proc.stderr)
    metrics["program_returncode"] = float(proc.returncode)

    submission_path = work_dir / "temp" / "submission.json"
    if not submission_path.exists():
        submission_path = work_dir / "submission.json"
    if not submission_path.exists():
        metrics["runtime_s"] = float(time.time() - start)
        metrics["combined_score"] = INVALID_COMBINED_SCORE
        metrics["valid"] = 0.0
        artifacts["error_message"] = "submission.json not found"
        shutil.rmtree(work_dir, ignore_errors=True)
        return _wrap(metrics, artifacts)

    with open(submission_path, "r", encoding="utf-8") as f:
        submission = json.load(f)
    artifacts["submission.json"] = json.dumps(submission, indent=2)

    if "solution_vector" not in submission:
        metrics["runtime_s"] = float(time.time() - start)
        metrics["combined_score"] = INVALID_COMBINED_SCORE
        metrics["valid"] = 0.0
        artifacts["error_message"] = "submission.json missing 'solution_vector'"
        shutil.rmtree(work_dir, ignore_errors=True)
        return _wrap(metrics, artifacts)

    max_eval = problem.get("optimization", {}).get("max_evaluations", None)
    num_eval = submission.get("num_evaluations", 0)
    if max_eval is not None and num_eval > max_eval:
        metrics["runtime_s"] = float(time.time() - start)
        metrics["valid"] = 0.0
        metrics["combined_score"] = INVALID_COMBINED_SCORE
        artifacts["error_message"] = f"Exceeded max evaluations: {num_eval} > {max_eval}"
        shutil.rmtree(work_dir, ignore_errors=True)
        return _wrap(metrics, artifacts)

    result = build_fem_and_evaluate(submission["solution_vector"], problem, repo_root)
    artifacts["evaluation_result"] = json.dumps(result, indent=2)

    runtime_s = time.time() - start
    objective = result.get("objective", 0.0)
    feasible = result.get("feasible", False)
    
    metrics["weight_kg"] = objective
    metrics["runtime_s"] = float(runtime_s)
    metrics["feasible"] = 1.0 if feasible else 0.0
    metrics["max_stress_violation"] = result.get("max_stress_violation", 0.0)
    metrics["max_displacement_violation"] = result.get(
        "max_displacement_violation", 0.0
    )

    if feasible and np.isfinite(objective) and objective > 0:
        metrics["combined_score"] = -float(objective)
        metrics["valid"] = 1.0
    else:
        metrics["combined_score"] = INVALID_COMBINED_SCORE
        metrics["valid"] = 0.0

    shutil.rmtree(work_dir, ignore_errors=True)
    return _wrap(metrics, artifacts)


def _wrap(metrics: dict[str, float], artifacts: dict[str, str]) -> Any:
    from openevolve.evaluation_result import EvaluationResult
    return EvaluationResult(metrics=metrics, artifacts=artifacts)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python evaluator.py <program_path>")
        print("  or:  python evaluator.py --test <submission.json>")
        sys.exit(1)

    if sys.argv[1] == "--test" and len(sys.argv) >= 3:
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            sub = json.load(f)
        repo = _find_repo_root()
        prob = load_problem_data(repo)
        result = build_fem_and_evaluate(sub["solution_vector"], prob, repo)
        print(json.dumps(result, indent=2))
    else:
        result = evaluate(sys.argv[1])
        if hasattr(result, "metrics"):
            output = {"metrics": result.metrics, "artifacts": result.artifacts}
        else:
            output = result
        print(json.dumps(output, indent=2))

