from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def _is_repo_root(path: Path) -> bool:
    if not (path / "frontier_eval").is_dir():
        return False
    if (path / "benchmarks").is_dir():
        return True
    return (path / "Astrodynamics").is_dir() and (path / "ElectronicDesignAutomation").is_dir()


def _find_repo_root() -> Path:
    if "FRONTIER_ENGINEERING_ROOT" in os.environ:
        return Path(os.environ["FRONTIER_ENGINEERING_ROOT"]).expanduser().resolve()

    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _is_repo_root(parent):
            return parent
    return Path.cwd().resolve()


def _tail(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _truncate_middle(text: str, limit: int = 200_000) -> str:
    if len(text) <= limit:
        return text
    keep = max(0, (limit - 128) // 2)
    omitted = len(text) - (2 * keep)
    return text[:keep] + f"\n\n[... truncated {omitted} chars ...]\n\n" + text[-keep:]


def _resolve_octave_executable() -> str | None:
    candidate_paths: list[Path] = []
    seen: set[str] = set()

    for env_name in (
        "FRONTIER_EVAL_UNIFIED_OCTAVE_EXECUTABLE",
        "FRONTIER_EVAL_UNIFIED_OCTAVE",
        "OCTAVE",
    ):
        raw = str(os.environ.get(env_name, "") or "").strip()
        if raw:
            candidate_paths.append(Path(raw).expanduser())

    for prefix_raw in (os.environ.get("CONDA_PREFIX", ""), sys.prefix):
        prefix = str(prefix_raw or "").strip()
        if not prefix:
            continue
        prefix_path = Path(prefix).expanduser()
        candidate_paths.append(prefix_path / "bin" / "octave-cli")
        candidate_paths.append(prefix_path / "bin" / "octave")

    for name in ("octave-cli", "octave"):
        resolved = shutil.which(name)
        if resolved:
            candidate_paths.append(Path(resolved).expanduser())

    for candidate in candidate_paths:
        path = candidate.expanduser()
        if not path.is_absolute():
            path = path.resolve()
        key = os.path.realpath(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def _octave_support_roots() -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()
    prefix_candidates = (
        os.environ.get("OCTAVE_HOME", ""),
        os.environ.get("CONDA_PREFIX", ""),
        sys.prefix,
    )
    for raw_prefix in prefix_candidates:
        prefix = str(raw_prefix or "").strip()
        if not prefix:
            continue
        prefix_path = Path(prefix).expanduser()
        for candidate in sorted((prefix_path / "share" / "octave").glob("*/m")):
            key = candidate.as_posix()
            if key in seen or not candidate.is_dir():
                continue
            seen.add(key)
            roots.append(candidate)
        site_m = prefix_path / "share" / "octave" / "site" / "m"
        key = site_m.as_posix()
        if key not in seen and site_m.is_dir():
            seen.add(key)
            roots.append(site_m)
    return roots


def evaluate(program_path: str, *, repo_root: Path | None = None):
    """
    OpenEvolve Evaluator for benchmarks/Astrodynamics/MannedLunarLanding.

    - Runs the candidate program to generate `results.txt`
    - Runs Octave validator `aerodynamics_check_octave_full.m`
    - Parses `outputlog.txt` for pass/fail and payload
    """
    start = time.time()
    repo_root = _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    program_path = str(Path(program_path).expanduser().resolve())

    work_dir = Path(tempfile.mkdtemp(prefix="fe_mll_")).resolve()
    artifacts: dict[str, str] = {}

    try:
        # 1) Run candidate generator (Python)
        try:
            proc = subprocess.run(
                [sys.executable, str(program_path)],
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired as e:
            metrics = {
                "combined_score": 0.0,
                "payload_kg": 0.0,
                "valid": 0.0,
                "timeout": 1.0,
                "runtime_s": float(time.time() - start),
            }
            artifacts["error_message"] = f"program timeout: {e}"
            return _wrap(metrics, artifacts)

        artifacts["program_stdout"] = _tail(proc.stdout)
        artifacts["program_stderr"] = _tail(proc.stderr)
        artifacts["program_stdout_full"] = _truncate_middle(proc.stdout)
        artifacts["program_stderr_full"] = _truncate_middle(proc.stderr)
        metrics: dict[str, float] = {
            "combined_score": 0.0,
            "payload_kg": 0.0,
            "valid": 0.0,
            "timeout": 0.0,
            "runtime_s": 0.0,
        }
        metrics["program_returncode"] = float(proc.returncode)

        results_path = work_dir / "results.txt"
        if not results_path.exists():
            artifacts["error_message"] = "results.txt not generated"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)
        try:
            artifacts["results.txt"] = results_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass

        # 2) Run Octave validator
        eval_dir = (repo_root / "benchmarks" / "Astrodynamics" / "MannedLunarLanding" / "eval").resolve()
        if not eval_dir.is_dir():
            eval_dir = (repo_root / "Astrodynamics" / "MannedLunarLanding" / "eval").resolve()
        if not eval_dir.is_dir():
            artifacts["error_message"] = f"eval dir not found: {eval_dir}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        octave_prelude = []
        for root in _octave_support_roots():
            octave_prelude.append(f"addpath(genpath('{root.as_posix()}')); ")
        octave_prelude.append(f"addpath('{eval_dir.as_posix()}'); ")
        octave_expr = "".join(octave_prelude) + "aerodynamics_check_octave_full; "
        octave_executable = _resolve_octave_executable()
        if not octave_executable:
            artifacts["error_message"] = "octave executable not found"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        octave_cmd = [octave_executable]
        if not Path(octave_executable).name.startswith("octave-cli"):
            octave_cmd.append("--no-gui")
        octave_cmd.extend(["--quiet", "--eval", octave_expr])
        artifacts["octave_executable"] = octave_executable
        artifacts["octave_command"] = " ".join(shlex.quote(part) for part in octave_cmd)

        try:
            proc2 = subprocess.run(
                ["bash", "-lc", artifacts["octave_command"]],
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=300,
            )
        except FileNotFoundError as e:
            artifacts["error_message"] = f"octave not found: {e}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)
        except subprocess.TimeoutExpired as e:
            artifacts["error_message"] = f"octave timeout: {e}"
            metrics["timeout"] = 1.0
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        artifacts["octave_stdout"] = _tail(proc2.stdout)
        artifacts["octave_stderr"] = _tail(proc2.stderr)
        artifacts["octave_stdout_full"] = _truncate_middle(proc2.stdout)
        artifacts["octave_stderr_full"] = _truncate_middle(proc2.stderr)
        metrics["octave_returncode"] = float(proc2.returncode)

        log_path = work_dir / "outputlog.txt"
        log_text = ""
        if log_path.exists():
            try:
                log_text = log_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                log_text = ""
        if log_text:
            artifacts["outputlog.txt"] = log_text
        artifacts["outputlog_tail"] = _tail(log_text)

        passed = "=====结果文件全部检验通过=====" in log_text
        payload = 0.0
        if passed:
            m = re.search(r"飞船运载质量：([0-9.]+)\s*kg", log_text)
            if m:
                payload = float(m.group(1))
        else:
            # try stderr/stdout fallback
            combined = "\n".join([proc2.stdout, proc2.stderr])
            m = re.search(r"飞船运载质量：([0-9.]+)\s*kg", combined)
            if m:
                payload = float(m.group(1))

        runtime_s = time.time() - start
        metrics["payload_kg"] = float(payload)
        metrics["runtime_s"] = float(runtime_s)

        if passed:
            metrics["combined_score"] = float(payload)
            metrics["valid"] = 1.0

        return _wrap(metrics, artifacts)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _wrap(metrics: dict[str, float], artifacts: dict[str, str]):
    try:
        from openevolve.evaluation_result import EvaluationResult
    except Exception:
        return {"metrics": metrics, "artifacts": artifacts}
    return EvaluationResult(metrics=metrics, artifacts=artifacts)
