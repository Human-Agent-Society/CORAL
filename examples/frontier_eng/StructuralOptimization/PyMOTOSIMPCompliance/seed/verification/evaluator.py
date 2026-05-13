"""Evaluator for PyMOTOSIMPCompliance (portable NumPy-only version)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np


VOL_TOL = 1e-3


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


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _load_problem_config(repo_root: Path) -> dict[str, Any]:
    candidates = [
        repo_root / "benchmarks" / "StructuralOptimization" / "PyMOTOSIMPCompliance" / "references" / "problem_config.json",
        repo_root / "StructuralOptimization" / "PyMOTOSIMPCompliance" / "references" / "problem_config.json",
    ]
    for p in candidates:
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError("problem_config.json not found")


def _element_stiffness_matrix(nu: float) -> np.ndarray:
    k = np.array(
        [
            0.5 - nu / 6.0,
            0.125 + nu / 8.0,
            -0.25 - nu / 12.0,
            -0.125 + 3.0 * nu / 8.0,
            -0.25 + nu / 12.0,
            -0.125 - nu / 8.0,
            nu / 6.0,
            0.125 - 3.0 * nu / 8.0,
        ],
        dtype=float,
    )
    ke = (1.0 / (1.0 - nu**2)) * np.array(
        [
            [k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7]],
            [k[1], k[0], k[7], k[6], k[5], k[4], k[3], k[2]],
            [k[2], k[7], k[0], k[5], k[6], k[3], k[4], k[1]],
            [k[3], k[6], k[5], k[0], k[7], k[2], k[1], k[4]],
            [k[4], k[5], k[6], k[7], k[0], k[1], k[2], k[3]],
            [k[5], k[4], k[3], k[2], k[1], k[0], k[7], k[6]],
            [k[6], k[3], k[4], k[1], k[2], k[7], k[0], k[5]],
            [k[7], k[2], k[1], k[4], k[3], k[6], k[5], k[0]],
        ],
        dtype=float,
    )
    return ke


def _fem_solve_dense(nelx: int, nely: int, x: np.ndarray, cfg: dict[str, Any]) -> np.ndarray:
    e0 = float(cfg["E0"])
    emin = float(cfg["Emin"])
    penal = float(cfg["penal"])
    nu = float(cfg["nu"])
    force_mag = float(cfg.get("force_magnitude", -1.0))
    if abs(force_mag) < 1e-12:
        force_mag = -1.0

    ke = _element_stiffness_matrix(nu)
    ndof = 2 * (nelx + 1) * (nely + 1)
    k_global = np.zeros((ndof, ndof), dtype=float)

    for elx in range(nelx):
        for ely in range(nely):
            n1 = elx * (nely + 1) + ely
            n2 = (elx + 1) * (nely + 1) + ely
            edof = np.array(
                [
                    2 * n1,
                    2 * n1 + 1,
                    2 * n2,
                    2 * n2 + 1,
                    2 * n2 + 2,
                    2 * n2 + 3,
                    2 * n1 + 2,
                    2 * n1 + 3,
                ],
                dtype=int,
            )
            ee = emin + (x[ely, elx] ** penal) * (e0 - emin)
            k_global[np.ix_(edof, edof)] += ee * ke

    f = np.zeros(ndof, dtype=float)
    load_node = nelx * (nely + 1) + (nely // 2)
    load_dof = 2 * load_node + int(cfg.get("force_direction", 1))
    f[load_dof] = force_mag

    fixed = []
    for j in range(nely + 1):
        node = j
        fixed.extend([2 * node, 2 * node + 1])
    fixed = np.array(sorted(set(fixed)), dtype=int)
    free = np.setdiff1d(np.arange(ndof, dtype=int), fixed)

    k_ff = k_global[np.ix_(free, free)]
    f_f = f[free]

    u = np.zeros(ndof, dtype=float)
    reg = 1e-9 * np.eye(k_ff.shape[0], dtype=float)
    u[free] = np.linalg.solve(k_ff + reg, f_f)
    return u


def _compliance(nelx: int, nely: int, x: np.ndarray, u: np.ndarray, cfg: dict[str, Any]) -> float:
    e0 = float(cfg["E0"])
    emin = float(cfg["Emin"])
    penal = float(cfg["penal"])
    nu = float(cfg["nu"])
    ke = _element_stiffness_matrix(nu)

    c = 0.0
    for elx in range(nelx):
        for ely in range(nely):
            n1 = elx * (nely + 1) + ely
            n2 = (elx + 1) * (nely + 1) + ely
            edof = np.array(
                [
                    2 * n1,
                    2 * n1 + 1,
                    2 * n2,
                    2 * n2 + 1,
                    2 * n2 + 2,
                    2 * n2 + 3,
                    2 * n1 + 2,
                    2 * n1 + 3,
                ],
                dtype=int,
            )
            ue = u[edof]
            ce = float(ue @ ke @ ue)
            ee = emin + (x[ely, elx] ** penal) * (e0 - emin)
            c += ee * ce
    return float(c)


def _evaluate_density(density_vector: list[float], cfg: dict[str, Any]) -> dict[str, Any]:
    nelx = int(cfg["nelx"])
    nely = int(cfg["nely"])
    rho_min = float(cfg.get("rho_min", 1e-9))

    arr = np.asarray(density_vector, dtype=float)
    expected = nelx * nely
    if arr.size != expected:
        return {
            "compliance": float("inf"),
            "volume_fraction": 0.0,
            "feasible": False,
            "error": f"Expected {expected} values, got {arr.size}",
        }
    if not np.all(np.isfinite(arr)):
        return {
            "compliance": float("inf"),
            "volume_fraction": 0.0,
            "feasible": False,
            "error": "density contains non-finite values",
        }

    x = np.clip(arr.reshape((nely, nelx)), rho_min, 1.0)
    volume_fraction = float(np.mean(x))
    feasible = bool(volume_fraction <= float(cfg["volfrac"]) + VOL_TOL)

    try:
        u = _fem_solve_dense(nelx, nely, x, cfg)
        compliance = _compliance(nelx, nely, x, u, cfg)
    except Exception as exc:
        return {
            "compliance": float("inf"),
            "volume_fraction": volume_fraction,
            "feasible": False,
            "error": f"FEM/compliance failed: {exc}",
        }

    return {
        "compliance": float(compliance),
        "volume_fraction": volume_fraction,
        "feasible": feasible,
    }


def _wrap(metrics: dict[str, float], artifacts: dict[str, Any]) -> Any:
    try:
        from openevolve.evaluation_result import EvaluationResult
    except Exception:
        return {"metrics": metrics, "artifacts": artifacts}
    return EvaluationResult(metrics=metrics, artifacts=artifacts)


def evaluate(program_path: str, *, repo_root: Path | None = None, timeout_s: float = 300.0) -> Any:
    start_s = time.time()
    repo = _find_repo_root() if repo_root is None else repo_root.resolve()
    bench = (repo / "benchmarks" / "StructuralOptimization" / "PyMOTOSIMPCompliance").resolve()

    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "valid": 0.0,
        "runtime_s": 0.0,
        "timeout": 0.0,
    }
    artifacts: dict[str, Any] = {
        "benchmark_dir": str(bench),
        "candidate_program": str(Path(program_path).expanduser().resolve()),
    }

    cfg = _load_problem_config(repo)

    uniform = np.full(int(cfg["nelx"] * cfg["nely"]), float(cfg["volfrac"]), dtype=float)
    base_eval = _evaluate_density(uniform.tolist(), cfg)
    base_c = _safe_float(base_eval.get("compliance"), float("inf"))

    candidate = Path(program_path).expanduser().resolve()
    if not candidate.is_file():
        artifacts["error_message"] = f"Candidate program not found: {candidate}"
        metrics["runtime_s"] = float(time.time() - start_s)
        return _wrap(metrics, artifacts)

    sub_path = bench / "temp" / "submission.json"
    sub_path.parent.mkdir(parents=True, exist_ok=True)
    if sub_path.exists():
        sub_path.unlink()

    cmd = [sys.executable, str(candidate)]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(bench),
            capture_output=True,
            text=True,
            timeout=max(1.0, float(timeout_s)),
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as exc:
        metrics["timeout"] = 1.0
        artifacts["error_message"] = f"candidate timeout: {exc}"
        metrics["runtime_s"] = float(time.time() - start_s)
        return _wrap(metrics, artifacts)

    artifacts["candidate_stdout"] = _tail(proc.stdout)
    artifacts["candidate_stderr"] = _tail(proc.stderr)
    artifacts["candidate_stdout_full"] = _truncate_middle(proc.stdout)
    artifacts["candidate_stderr_full"] = _truncate_middle(proc.stderr)
    metrics["candidate_returncode"] = float(proc.returncode)

    if proc.returncode != 0:
        artifacts["error_message"] = f"candidate exited with code {proc.returncode}"
        metrics["runtime_s"] = float(time.time() - start_s)
        return _wrap(metrics, artifacts)

    if not sub_path.is_file():
        artifacts["error_message"] = f"missing submission file: {sub_path}"
        metrics["runtime_s"] = float(time.time() - start_s)
        return _wrap(metrics, artifacts)

    try:
        submission = json.loads(sub_path.read_text(encoding="utf-8"))
    except Exception as exc:
        artifacts["error_message"] = f"invalid submission JSON: {exc}"
        metrics["runtime_s"] = float(time.time() - start_s)
        return _wrap(metrics, artifacts)

    density_vector = submission.get("density_vector")
    if not isinstance(density_vector, list):
        artifacts["error_message"] = "submission must contain list field `density_vector`"
        metrics["runtime_s"] = float(time.time() - start_s)
        return _wrap(metrics, artifacts)

    eval_result = _evaluate_density(density_vector, cfg)
    comp = _safe_float(eval_result.get("compliance"), float("inf"))
    vfrac = _safe_float(eval_result.get("volume_fraction"), 0.0)
    feasible = bool(eval_result.get("feasible", False))

    metrics["compliance"] = comp
    metrics["volume_fraction"] = vfrac
    metrics["feasible"] = 1.0 if feasible else 0.0
    metrics["baseline_uniform_compliance"] = base_c

    if feasible and np.isfinite(comp) and comp > 0.0 and np.isfinite(base_c) and base_c > 0.0:
        score = float(base_c / comp)
        metrics["combined_score"] = score
        metrics["score_ratio"] = score
        metrics["valid"] = 1.0
    else:
        metrics["combined_score"] = 0.0
        metrics["score_ratio"] = 0.0
        metrics["valid"] = 0.0

    if "error" in eval_result:
        artifacts["error_message"] = str(eval_result["error"])

    artifacts["submission_path"] = str(sub_path)
    artifacts["reported_compliance"] = submission.get("compliance")
    artifacts["reported_volume_fraction"] = submission.get("volume_fraction")

    metrics["runtime_s"] = float(time.time() - start_s)
    return _wrap(metrics, artifacts)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a PyMOTOSIMPCompliance candidate")
    parser.add_argument("program_path", help="Path to candidate program")
    parser.add_argument("--timeout-s", type=float, default=300.0)
    parser.add_argument("--metrics-out", default="")
    parser.add_argument("--artifacts-out", default="")
    parser.add_argument("--stdout-out", default="")
    parser.add_argument("--stderr-out", default="")
    parser.add_argument("--run-meta-out", default="")
    args = parser.parse_args()

    result = evaluate(args.program_path, timeout_s=float(args.timeout_s))
    if isinstance(result, dict):
        metrics = result.get("metrics", {}) if isinstance(result.get("metrics"), dict) else {}
        artifacts = result.get("artifacts", {}) if isinstance(result.get("artifacts"), dict) else {}
    else:
        metrics = getattr(result, "metrics", {}) if isinstance(getattr(result, "metrics", {}), dict) else {}
        artifacts = getattr(result, "artifacts", {}) if isinstance(getattr(result, "artifacts", {}), dict) else {}

    payload = {
        "combined_score": _safe_float(metrics.get("combined_score"), 0.0),
        "valid": _safe_float(metrics.get("valid"), 0.0),
        "runtime_s": _safe_float(metrics.get("runtime_s"), 0.0),
    }
    payload.update({k: v for k, v in metrics.items() if k not in payload})

    if args.stdout_out:
        Path(args.stdout_out).write_text(
            str(artifacts.get("candidate_stdout_full", artifacts.get("candidate_stdout", ""))),
            encoding="utf-8",
            errors="replace",
        )
    if args.stderr_out:
        Path(args.stderr_out).write_text(
            str(artifacts.get("candidate_stderr_full", artifacts.get("candidate_stderr", ""))),
            encoding="utf-8",
            errors="replace",
        )

    if args.metrics_out:
        _write_json(Path(args.metrics_out), payload)
    if args.artifacts_out:
        _write_json(Path(args.artifacts_out), artifacts)
    if args.run_meta_out:
        lines = [
            f"candidate={Path(args.program_path).expanduser().resolve()}",
            f"combined_score={payload.get('combined_score', 0.0)}",
            f"valid={payload.get('valid', 0.0)}",
            f"runtime_s={payload.get('runtime_s', 0.0)}",
        ]
        Path(args.run_meta_out).write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("valid", 0.0) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
