from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from spec import CryptographicSpec


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


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _openssl_header_present(include_dir: Path) -> bool:
    return any(
        (include_dir / header_rel).is_file()
        for header_rel in ("openssl/evp.h", "openssl/sha.h", "openssl/rand.h")
    )


def _libcrypto_present(lib_dir: Path) -> bool:
    return any(
        (lib_dir / lib_name).exists()
        for lib_name in ("libcrypto.so", "libcrypto.so.3", "libcrypto.dylib", "libcrypto.a", "libcrypto.lib")
    )


def _discover_openssl_paths() -> tuple[list[str], list[str], dict[str, str]]:
    prefix_values = [
        os.environ.get("CONDA_PREFIX"),
        sys.prefix,
        "/usr",
        "/usr/local",
        "/opt/homebrew",
        "/opt/local",
    ]

    prefix_candidates: list[Path] = []
    include_candidates: list[Path] = []
    lib_candidates: list[Path] = []
    seen_prefixes: set[str] = set()

    def _append_unique(target: list[Path], raw_path: Path) -> None:
        try:
            path = raw_path.expanduser().resolve()
        except Exception:
            path = raw_path.expanduser()
        if not path.is_dir() or path in target:
            return
        target.append(path)

    for raw_prefix in prefix_values:
        if not raw_prefix:
            continue
        try:
            prefix = Path(raw_prefix).expanduser().resolve()
        except Exception:
            prefix = Path(raw_prefix).expanduser()
        key = str(prefix)
        if key in seen_prefixes:
            continue
        seen_prefixes.add(key)
        prefix_candidates.append(prefix)
        _append_unique(include_candidates, prefix / "include")
        _append_unique(lib_candidates, prefix / "lib")
        _append_unique(lib_candidates, prefix / "lib64")

    for extra_include in ("/usr/include", "/usr/local/include"):
        _append_unique(include_candidates, Path(extra_include))
    for extra_lib in (
        "/usr/lib",
        "/usr/lib64",
        "/usr/lib/x86_64-linux-gnu",
        "/usr/local/lib",
        "/usr/local/lib64",
        "/lib",
        "/lib64",
        "/lib/x86_64-linux-gnu",
    ):
        _append_unique(lib_candidates, Path(extra_lib))

    include_dir = next((path for path in include_candidates if _openssl_header_present(path)), None)
    lib_dir = next((path for path in lib_candidates if _libcrypto_present(path)), None)

    compile_flags: list[str] = []
    link_flags: list[str] = []
    debug_artifacts: dict[str, str] = {
        "openssl_prefix_candidates": "\n".join(str(path) for path in prefix_candidates),
        "openssl_include_candidates": "\n".join(str(path) for path in include_candidates),
        "openssl_lib_candidates": "\n".join(str(path) for path in lib_candidates),
    }

    if include_dir is not None:
        compile_flags.extend(["-isystem", str(include_dir)])
        debug_artifacts["openssl_include_dir"] = str(include_dir)
    if lib_dir is not None:
        link_flags.extend(["-L", str(lib_dir), f"-Wl,-rpath,{lib_dir}"])
        debug_artifacts["openssl_lib_dir"] = str(lib_dir)

    return compile_flags, link_flags, debug_artifacts


def _remaining_timeout(deadline_s: float) -> float:
    return max(1.0, float(deadline_s - time.time()))


def _safe_metric_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower() or "case"


def _parse_validation_pass_counts(text: str) -> tuple[float | None, float | None]:
    patterns = [
        r"Verification Complete:\s*([0-9]+)\s*/\s*([0-9]+)\s*passed",
        r"通过率[:：]\s*([0-9]+)\s*/\s*([0-9]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue
        try:
            return float(m.group(1)), float(m.group(2))
        except Exception:
            continue
    return None, None


def _validation_has_fail_marker(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"\[FAIL\]|Failed to execute|Unexpected output", text, flags=re.IGNORECASE))


def _parse_throughputs(text: str) -> tuple[dict[str, float], dict[str, str]]:
    by_case: dict[str, float] = {}
    current_case = ""

    for raw in (text or "").splitlines():
        line = raw.strip()
        if line.startswith("Benchmark:"):
            current_case = line.split(":", 1)[1].strip()
            continue
        m = re.search(r"Throughput\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*Mbps", line, flags=re.IGNORECASE)
        if not m:
            continue
        try:
            value = float(m.group(1))
        except Exception:
            continue
        key = current_case or f"case_{len(by_case) + 1}"
        by_case[key] = value

    metrics: dict[str, float] = {}
    artifacts: dict[str, str] = {}
    if not by_case:
        return metrics, artifacts

    values = [max(float(v), 1e-30) for v in by_case.values()]
    gmean = float(math.exp(sum(math.log(v) for v in values) / len(values)))
    mean = float(sum(by_case.values()) / len(by_case))
    metrics["benchmark_count"] = float(len(by_case))
    metrics["throughput_geom_mean_mbps"] = gmean
    metrics["throughput_mean_mbps"] = mean
    metrics["combined_score"] = gmean

    for name, value in by_case.items():
        metrics[f"throughput_{_safe_metric_key(name)}_mbps"] = float(value)

    for name, value in by_case.items():
        lower = name.lower().replace(" ", "")
        if "8kbits" in lower:
            metrics["throughput_8kbits_mbps"] = float(value)
        if "8mbits" in lower:
            metrics["throughput_8mbits_mbps"] = float(value)

    artifacts["throughput_by_case"] = "\n".join(
        f"{name}: {value:.6f} Mbps" for name, value in by_case.items()
    )
    return metrics, artifacts


def _extract_pdf_text(pdf_path: Path, *, deadline_s: float) -> tuple[str | None, str | None]:
    cmd = ["pdftotext", "-q", "-layout", str(pdf_path), "-"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=min(30.0, _remaining_timeout(deadline_s)),
        )
    except FileNotFoundError:
        return None, "pdftotext not found"
    except subprocess.TimeoutExpired as e:
        return None, f"pdftotext timeout: {e}"

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        return None, f"pdftotext failed (code={proc.returncode}): {stderr}"

    text = (proc.stdout or "").strip()
    if not text:
        return None, "pdftotext produced empty output"
    return text, None


def evaluate(
    program_path: str,
    *,
    repo_root: Path | None = None,
    spec: CryptographicSpec,
    include_pdf_reference: bool = False,
) -> Any:
    """
    OpenEvolve evaluator for benchmarks/Cryptographic/*.

    Contract:
    - Candidate file replaces `baseline/<source>.cpp` in a temporary sandbox.
    - Correctness is validated by `verification/validate.cpp`.
    - Throughput is measured by `verification/evaluate.cpp`.
    - Final score is geometric mean throughput (Mbps) across benchmark cases.
    """
    start = time.time()
    repo_root = _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    program_path_p = Path(program_path).expanduser().resolve()

    benchmark_dir = spec.benchmark_dir(repo_root)
    baseline_dir = (benchmark_dir / "baseline").resolve()
    verification_dir = (benchmark_dir / "verification").resolve()
    task_spec_zh_cn_path = (benchmark_dir / "Task_zh-CN.md").resolve()
    reference_pdf_path = (benchmark_dir / "references" / spec.reference_pdf).resolve()

    artifacts: dict[str, str] = {}
    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "valid": 0.0,
        "timeout": 0.0,
        "runtime_s": 0.0,
    }
    artifacts["interface_contract"] = (
        "Hard requirements for candidate program (do NOT change these):\n"
        f"1) Candidate must be valid C++ source for baseline/{spec.baseline_source}.\n"
        "2) Evaluator compiles candidate with `g++ -std=c++17 -O3`.\n"
        "3) Evaluator then runs correctness check binary built from verification/validate.cpp.\n"
        "4) Evaluator runs performance benchmark built from verification/evaluate.cpp.\n"
        "5) Final `combined_score` is geometric mean throughput in Mbps across reported cases.\n"
        "6) If correctness fails, `valid=0` and `combined_score=0`."
    )
    artifacts["task_spec_zh_cn_path"] = str(task_spec_zh_cn_path)
    task_spec_zh_cn = _read_text(task_spec_zh_cn_path)
    if task_spec_zh_cn:
        artifacts["task_spec_zh_cn"] = _truncate_middle(task_spec_zh_cn)

    evaluator_timeout_s = float(os.environ.get("FRONTIER_EVAL_EVALUATOR_TIMEOUT_S", "600") or "600")
    deadline_s = start + max(1.0, evaluator_timeout_s - 5.0)
    if include_pdf_reference:
        artifacts["reference_pdf_path"] = str(reference_pdf_path)
        if reference_pdf_path.is_file():
            pdf_text, pdf_error = _extract_pdf_text(reference_pdf_path, deadline_s=deadline_s)
            if pdf_text:
                artifacts["reference_pdf_text"] = _truncate_middle(pdf_text, limit=150_000)
            elif pdf_error:
                artifacts["reference_pdf_error"] = pdf_error
        else:
            artifacts["reference_pdf_error"] = f"reference PDF not found: {reference_pdf_path}"

    if not benchmark_dir.is_dir() or not baseline_dir.is_dir() or not verification_dir.is_dir():
        artifacts["error_message"] = (
            f"cryptographic benchmark folder missing: benchmark={benchmark_dir}, "
            f"baseline={baseline_dir}, verification={verification_dir}"
        )
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    if not program_path_p.is_file():
        artifacts["error_message"] = f"candidate program not found: {program_path_p}"
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    work_dir = Path(tempfile.mkdtemp(prefix=f"fe_{spec.benchmark_subdir.lower().replace('-', '_')}_")).resolve()
    try:
        sandbox_dir = (work_dir / spec.benchmark_subdir).resolve()
        sandbox_baseline = (sandbox_dir / "baseline").resolve()
        sandbox_verification = (sandbox_dir / "verification").resolve()
        shutil.copytree(baseline_dir, sandbox_baseline)
        shutil.copytree(verification_dir, sandbox_verification)

        candidate_dst = (sandbox_baseline / spec.baseline_source).resolve()
        shutil.copy2(program_path_p, candidate_dst)
        artifacts["candidate_program"] = str(candidate_dst)

        custom_binary = (sandbox_verification / spec.custom_binary).resolve()
        validate_binary = (sandbox_verification / "validate").resolve()
        evaluate_binary = (sandbox_verification / "evaluate").resolve()

        compile_candidate_cmd = [
            "g++",
            "-std=c++17",
            "-O3",
            str(candidate_dst),
            "-o",
            str(custom_binary),
        ]
        artifacts["compile_candidate_cmd"] = " ".join(compile_candidate_cmd)
        try:
            proc_compile_candidate = subprocess.run(
                compile_candidate_cmd,
                cwd=str(sandbox_verification),
                capture_output=True,
                text=True,
                timeout=_remaining_timeout(deadline_s),
            )
        except subprocess.TimeoutExpired as e:
            metrics["timeout"] = 1.0
            metrics["runtime_s"] = float(time.time() - start)
            artifacts["error_message"] = f"candidate compile timeout: {e}"
            return _wrap(metrics, artifacts)
        except FileNotFoundError as e:
            metrics["runtime_s"] = float(time.time() - start)
            artifacts["error_message"] = f"compiler unavailable: {e}"
            return _wrap(metrics, artifacts)

        metrics["compile_candidate_returncode"] = float(proc_compile_candidate.returncode)
        artifacts["compile_candidate_stdout"] = _tail(proc_compile_candidate.stdout)
        artifacts["compile_candidate_stderr"] = _tail(proc_compile_candidate.stderr)
        artifacts["compile_candidate_stdout_full"] = _truncate_middle(proc_compile_candidate.stdout)
        artifacts["compile_candidate_stderr_full"] = _truncate_middle(proc_compile_candidate.stderr)
        if proc_compile_candidate.returncode != 0:
            artifacts["error_message"] = "candidate compile failed"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        openssl_compile_flags, openssl_link_flags, openssl_debug = _discover_openssl_paths()
        artifacts.update(openssl_debug)
        if not openssl_compile_flags:
            artifacts["openssl_resolution_warning"] = (
                "No explicit OpenSSL include directory detected; falling back to compiler defaults"
            )
        if not openssl_link_flags:
            artifacts["openssl_resolution_warning"] = (
                artifacts.get("openssl_resolution_warning", "")
                + ("\n" if artifacts.get("openssl_resolution_warning") else "")
                + "No explicit libcrypto directory detected; falling back to linker defaults"
            )

        compile_validate_cmd = [
            "g++",
            "-std=c++17",
            "-O3",
            *openssl_compile_flags,
            str(sandbox_verification / "validate.cpp"),
            "-o",
            str(validate_binary),
            *openssl_link_flags,
            "-lcrypto",
        ]
        artifacts["compile_validate_cmd"] = " ".join(compile_validate_cmd)
        try:
            proc_compile_validate = subprocess.run(
                compile_validate_cmd,
                cwd=str(sandbox_verification),
                capture_output=True,
                text=True,
                timeout=_remaining_timeout(deadline_s),
            )
        except FileNotFoundError as e:
            metrics["runtime_s"] = float(time.time() - start)
            artifacts["error_message"] = f"compiler unavailable: {e}"
            return _wrap(metrics, artifacts)
        except subprocess.TimeoutExpired as e:
            metrics["timeout"] = 1.0
            metrics["runtime_s"] = float(time.time() - start)
            artifacts["error_message"] = f"validate compile timeout: {e}"
            return _wrap(metrics, artifacts)

        metrics["compile_validate_returncode"] = float(proc_compile_validate.returncode)
        artifacts["compile_validate_stdout"] = _tail(proc_compile_validate.stdout)
        artifacts["compile_validate_stderr"] = _tail(proc_compile_validate.stderr)
        artifacts["compile_validate_stdout_full"] = _truncate_middle(proc_compile_validate.stdout)
        artifacts["compile_validate_stderr_full"] = _truncate_middle(proc_compile_validate.stderr)
        if proc_compile_validate.returncode != 0:
            artifacts["error_message"] = "validate compile failed"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        validate_cmd = [str(validate_binary)]
        artifacts["validate_cmd"] = " ".join(validate_cmd)
        try:
            proc_validate = subprocess.run(
                validate_cmd,
                cwd=str(sandbox_verification),
                capture_output=True,
                text=True,
                timeout=_remaining_timeout(deadline_s),
            )
        except FileNotFoundError as e:
            metrics["runtime_s"] = float(time.time() - start)
            artifacts["error_message"] = f"validate executable unavailable: {e}"
            return _wrap(metrics, artifacts)
        except subprocess.TimeoutExpired as e:
            metrics["timeout"] = 1.0
            metrics["runtime_s"] = float(time.time() - start)
            artifacts["error_message"] = f"validate timeout: {e}"
            return _wrap(metrics, artifacts)

        metrics["validate_returncode"] = float(proc_validate.returncode)
        artifacts["validate_stdout"] = _tail(proc_validate.stdout)
        artifacts["validate_stderr"] = _tail(proc_validate.stderr)
        artifacts["validate_stdout_full"] = _truncate_middle(proc_validate.stdout)
        artifacts["validate_stderr_full"] = _truncate_middle(proc_validate.stderr)

        validate_text = "\n".join([proc_validate.stdout or "", proc_validate.stderr or ""])
        pass_count, total_count = _parse_validation_pass_counts(validate_text)
        if pass_count is not None and total_count is not None:
            metrics["validate_passed"] = pass_count
            metrics["validate_total"] = total_count
            if total_count > 0:
                metrics["validate_pass_rate"] = pass_count / total_count

        validation_failed = proc_validate.returncode != 0
        if (
            pass_count is not None
            and total_count is not None
            and total_count > 0
            and pass_count < total_count
        ):
            validation_failed = True
        if _validation_has_fail_marker(validate_text):
            validation_failed = True

        if validation_failed:
            metrics["runtime_s"] = float(time.time() - start)
            artifacts["error_message"] = "correctness validation failed"
            return _wrap(metrics, artifacts)

        compile_evaluate_cmd = [
            "g++",
            "-std=c++17",
            "-O3",
            str(sandbox_verification / "evaluate.cpp"),
            "-o",
            str(evaluate_binary),
        ]
        artifacts["compile_evaluate_cmd"] = " ".join(compile_evaluate_cmd)
        try:
            proc_compile_evaluate = subprocess.run(
                compile_evaluate_cmd,
                cwd=str(sandbox_verification),
                capture_output=True,
                text=True,
                timeout=_remaining_timeout(deadline_s),
            )
        except FileNotFoundError as e:
            metrics["runtime_s"] = float(time.time() - start)
            artifacts["error_message"] = f"compiler unavailable: {e}"
            return _wrap(metrics, artifacts)
        except subprocess.TimeoutExpired as e:
            metrics["timeout"] = 1.0
            metrics["runtime_s"] = float(time.time() - start)
            artifacts["error_message"] = f"evaluate compile timeout: {e}"
            return _wrap(metrics, artifacts)

        metrics["compile_evaluate_returncode"] = float(proc_compile_evaluate.returncode)
        artifacts["compile_evaluate_stdout"] = _tail(proc_compile_evaluate.stdout)
        artifacts["compile_evaluate_stderr"] = _tail(proc_compile_evaluate.stderr)
        artifacts["compile_evaluate_stdout_full"] = _truncate_middle(proc_compile_evaluate.stdout)
        artifacts["compile_evaluate_stderr_full"] = _truncate_middle(proc_compile_evaluate.stderr)
        if proc_compile_evaluate.returncode != 0:
            artifacts["error_message"] = "evaluate compile failed"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        benchmark_cmd = [str(evaluate_binary)]
        artifacts["benchmark_cmd"] = " ".join(benchmark_cmd)
        try:
            proc_benchmark = subprocess.run(
                benchmark_cmd,
                cwd=str(sandbox_verification),
                capture_output=True,
                text=True,
                timeout=_remaining_timeout(deadline_s),
            )
        except FileNotFoundError as e:
            metrics["runtime_s"] = float(time.time() - start)
            artifacts["error_message"] = f"benchmark executable unavailable: {e}"
            return _wrap(metrics, artifacts)
        except subprocess.TimeoutExpired as e:
            metrics["timeout"] = 1.0
            metrics["runtime_s"] = float(time.time() - start)
            artifacts["error_message"] = f"benchmark timeout: {e}"
            return _wrap(metrics, artifacts)

        metrics["benchmark_returncode"] = float(proc_benchmark.returncode)
        artifacts["benchmark_stdout"] = _tail(proc_benchmark.stdout)
        artifacts["benchmark_stderr"] = _tail(proc_benchmark.stderr)
        artifacts["benchmark_stdout_full"] = _truncate_middle(proc_benchmark.stdout)
        artifacts["benchmark_stderr_full"] = _truncate_middle(proc_benchmark.stderr)

        parsed_metrics, parsed_artifacts = _parse_throughputs(
            "\n".join([proc_benchmark.stdout or "", proc_benchmark.stderr or ""])
        )
        metrics.update(parsed_metrics)
        artifacts.update(parsed_artifacts)

        if proc_benchmark.returncode != 0:
            artifacts["error_message"] = "throughput benchmark failed"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)
        if "combined_score" not in metrics:
            artifacts["error_message"] = "failed to parse throughput from benchmark output"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        metrics["valid"] = 1.0
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _wrap(metrics: dict[str, float], artifacts: dict[str, str]) -> Any:
    try:
        from openevolve.evaluation_result import EvaluationResult
    except Exception:
        return {"metrics": metrics, "artifacts": artifacts}
    return EvaluationResult(metrics=metrics, artifacts=artifacts)
