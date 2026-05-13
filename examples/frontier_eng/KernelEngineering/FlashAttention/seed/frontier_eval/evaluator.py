from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
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


def _remaining_timeout(deadline_s: float) -> float:
    return max(1.0, float(deadline_s - time.time()))


def _parse_popcorn_log(log_text: str) -> tuple[dict[str, str], list[float], list[str]]:
    fields: dict[str, str] = {}
    mean_by_case: list[tuple[int, float]] = []
    failures: list[str] = []

    for raw in (log_text or "").splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        fields[key] = value

        m_mean = re.fullmatch(r"benchmark\.(\d+)\.mean", key)
        if m_mean:
            try:
                mean_by_case.append((int(m_mean.group(1)), float(value)))
            except Exception:
                continue

        if re.fullmatch(r"benchmark\.\d+\.error", key):
            failures.append(value)

    mean_by_case.sort(key=lambda x: x[0])
    return fields, [v for _, v in mean_by_case], failures


def _geometric_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    safe = [max(float(v), 1e-30) for v in values]
    return float(math.exp(sum(math.log(v) for v in safe) / len(safe)))


def _write_compat_runner(path: Path) -> None:
    path.write_text(
        "import builtins\n"
        "import sys\n"
        "\n"
        "try:\n"
        "    from baseline import task as _task\n"
        "    builtins.input_t = getattr(_task, 'input_t', tuple)\n"
        "    builtins.output_t = getattr(_task, 'output_t', tuple)\n"
        "except Exception:\n"
        "    builtins.input_t = tuple\n"
        "    builtins.output_t = tuple\n"
        "\n"
        "import eval as flash_eval\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    sys.exit(flash_eval.main())\n",
        encoding="utf-8",
    )


def evaluate(
    program_path: str,
    *,
    repo_root: Path | None = None,
    kernel_python: str | None = None,
):
    start = time.time()
    repo_root = _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    program_path = str(Path(program_path).expanduser().resolve())

    benchmark_dir = (repo_root / "benchmarks" / "KernelEngineering" / "FlashAttention").resolve()
    if not benchmark_dir.is_dir():
        benchmark_dir = (repo_root / "KernelEngineering" / "FlashAttention").resolve()
    baseline_dir = (benchmark_dir / "baseline").resolve()
    verification_dir = (benchmark_dir / "verification").resolve()

    artifacts: dict[str, str] = {}
    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "valid": 0.0,
        "timeout": 0.0,
        "runtime_s": 0.0,
        "benchmark_count": 0.0,
        "geom_mean_ns": 0.0,
    }
    artifacts["interface_contract"] = (
        "Hard requirements for candidate program (do NOT change these):\n"
        "1) Evaluator copies candidate file to baseline/submission.py and runs "
        "`python eval.py benchmark flash_attn_bench.txt`.\n"
        "2) Candidate MUST expose `custom_kernel(data)`.\n"
        "3) `data` is a 4-tuple `(config, Q, K, V)` produced by baseline/reference.py.\n"
        "4) Return attention output tensor of shape (B, H, N, D).\n"
        "5) Do not change evaluator CLI or test file names."
    )

    if not baseline_dir.is_dir() or not verification_dir.is_dir():
        artifacts["error_message"] = (
            f"FlashAttention benchmark folder missing: baseline={baseline_dir}, "
            f"verification={verification_dir}"
        )
        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)

    kernel_python = (
        str(kernel_python or "").strip()
        or str(os.environ.get("FRONTIER_EVAL_FLASH_ATTENTION_PYTHON", "") or "").strip()
        or "python"
    )
    artifacts["kernel_python"] = kernel_python

    work_dir = Path(tempfile.mkdtemp(prefix="fe_flash_attn_")).resolve()

    evaluator_timeout_s = float(os.environ.get("FRONTIER_EVAL_EVALUATOR_TIMEOUT_S", "1200") or "1200")
    deadline_s = start + max(1.0, evaluator_timeout_s - 5.0)

    try:
        sandbox_task_dir = (work_dir / "FlashAttention").resolve()
        sandbox_baseline = (sandbox_task_dir / "baseline").resolve()
        sandbox_verification = (sandbox_task_dir / "verification").resolve()
        shutil.copytree(baseline_dir, sandbox_baseline)
        shutil.copytree(verification_dir, sandbox_verification)

        candidate_dst = (sandbox_baseline / "submission.py").resolve()
        shutil.copy2(program_path, candidate_dst)
        artifacts["candidate_program"] = str(candidate_dst)

        log_path = (sandbox_verification / "flash_attn_bench.log").resolve()
        env = os.environ.copy()
        env.setdefault("FRONTIER_ENGINEERING_ROOT", str(repo_root))
        env.pop("POPCORN_FD", None)

        # CUDA probe
        cuda_probe_cmd = [
            kernel_python,
            "-c",
            (
                "import sys, torch; "
                "ok = bool(torch.cuda.is_available()) and int(torch.cuda.device_count()) > 0; "
                "print(f'is_available={torch.cuda.is_available()} device_count={torch.cuda.device_count()}'); "
                "sys.exit(0 if ok else 7)"
            ),
        ]
        try:
            probe = subprocess.run(
                cuda_probe_cmd,
                cwd=str(sandbox_verification),
                capture_output=True,
                text=True,
                timeout=min(30.0, _remaining_timeout(deadline_s)),
                env=env,
            )
            artifacts["cuda_probe_cmd"] = " ".join(cuda_probe_cmd)
            artifacts["cuda_probe_stdout"] = _tail(probe.stdout)
            artifacts["cuda_probe_stderr"] = _tail(probe.stderr)
            if probe.returncode != 0:
                artifacts["error_message"] = (
                    "CUDA is unavailable. "
                    "Ensure the benchmark runs on a GPU node."
                )
                metrics["runtime_s"] = float(time.time() - start)
                return _wrap(metrics, artifacts)
        except subprocess.TimeoutExpired as e:
            artifacts["error_message"] = f"cuda probe timeout: {e}"
            metrics["timeout"] = 1.0
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)
        except FileNotFoundError as e:
            artifacts["error_message"] = f"kernel python not found: {e}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        def _run_with_log(cmd: list[str]):
            fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            os.set_inheritable(fd, True)
            env["POPCORN_FD"] = str(fd)
            try:
                return subprocess.run(
                    cmd,
                    cwd=str(sandbox_verification),
                    capture_output=True,
                    text=True,
                    timeout=_remaining_timeout(deadline_s),
                    env=env,
                    pass_fds=(fd,),
                )
            finally:
                try:
                    os.close(fd)
                except Exception:
                    pass
                env.pop("POPCORN_FD", None)

        wrapper_path = (sandbox_verification / "_flash_eval_runner.py").resolve()
        _write_compat_runner(wrapper_path)

        cmd = [kernel_python, str(wrapper_path), "benchmark", "flash_attn_bench.txt"]
        artifacts["runner_mode"] = "compat_wrapper"
        artifacts["benchmark_cmd"] = " ".join(cmd)

        try:
            proc = _run_with_log(cmd)
        except FileNotFoundError as e:
            artifacts["error_message"] = f"kernel python not found: {e}"
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)
        except subprocess.TimeoutExpired as e:
            artifacts["error_message"] = f"benchmark timeout: {e}"
            metrics["timeout"] = 1.0
            metrics["runtime_s"] = float(time.time() - start)
            return _wrap(metrics, artifacts)

        # SemLock fallback (same pattern as MLA)
        if proc.returncode != 0 and "PermissionError" in proc.stderr and "SemLock" in proc.stderr:
            wrapper_path = (sandbox_verification / "_serial_eval_runner.py").resolve()
            wrapper_path.write_text(
                "import multiprocessing\n"
                "import builtins\n"
                "import sys\n"
                "\n"
                "class _SerialPool:\n"
                "    def __enter__(self):\n"
                "        return self\n"
                "    def __exit__(self, exc_type, exc_val, exc_tb):\n"
                "        return False\n"
                "    def apply(self, fn, args=(), kwds=None):\n"
                "        kwds = {} if kwds is None else kwds\n"
                "        return fn(*args, **kwds)\n"
                "\n"
                "class _Ctx:\n"
                "    def Pool(self, *_args, **_kwargs):\n"
                "        return _SerialPool()\n"
                "\n"
                "def _get_context(_method='spawn'):\n"
                "    return _Ctx()\n"
                "\n"
                "multiprocessing.get_context = _get_context\n"
                "\n"
                "try:\n"
                "    from baseline import task as _task\n"
                "    builtins.input_t = getattr(_task, 'input_t', tuple)\n"
                "    builtins.output_t = getattr(_task, 'output_t', tuple)\n"
                "except Exception:\n"
                "    builtins.input_t = tuple\n"
                "    builtins.output_t = tuple\n"
                "\n"
                "import eval as flash_eval\n"
                "\n"
                "if __name__ == '__main__':\n"
                "    sys.exit(flash_eval.main())\n",
                encoding="utf-8",
            )
            cmd = [kernel_python, str(wrapper_path), "benchmark", "flash_attn_bench.txt"]
            artifacts["runner_mode"] = "serial_fallback"
            artifacts["benchmark_cmd"] = " ".join(cmd)
            artifacts["fallback_reason"] = "PermissionError SemLock"
            try:
                proc = _run_with_log(cmd)
            except subprocess.TimeoutExpired as e:
                artifacts["error_message"] = f"benchmark timeout (serial fallback): {e}"
                metrics["timeout"] = 1.0
                metrics["runtime_s"] = float(time.time() - start)
                return _wrap(metrics, artifacts)

        artifacts["benchmark_stdout"] = _tail(proc.stdout)
        artifacts["benchmark_stderr"] = _tail(proc.stderr)
        artifacts["benchmark_stdout_full"] = _truncate_middle(proc.stdout)
        artifacts["benchmark_stderr_full"] = _truncate_middle(proc.stderr)
        metrics["benchmark_returncode"] = float(proc.returncode)

        log_text = ""
        if log_path.is_file():
            try:
                log_text = log_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                log_text = ""
        artifacts["flash_attn_bench.log_tail"] = _tail(log_text)
        if log_text:
            artifacts["flash_attn_bench.log"] = _truncate_middle(log_text)

        fields, means_ns, failures = _parse_popcorn_log(log_text)
        if fields.get("check") is not None:
            artifacts["check"] = fields.get("check", "")
        if failures:
            artifacts["failure_summary"] = "\n".join(failures[:8])

        if means_ns:
            gmean_ns = _geometric_mean(means_ns)
            metrics["benchmark_count"] = float(len(means_ns))
            metrics["geom_mean_ns"] = float(gmean_ns)
            metrics["best_case_ns"] = float(min(means_ns))
            metrics["worst_case_ns"] = float(max(means_ns))

            if gmean_ns > 0:
                metrics["combined_score"] = float(1e9 / gmean_ns)

        passed = (
            proc.returncode == 0
            and fields.get("check", "").strip().lower() == "pass"
            and bool(means_ns)
        )
        if passed:
            metrics["valid"] = 1.0
        else:
            metrics["valid"] = 0.0
            metrics["combined_score"] = 0.0
            if "error_message" not in artifacts:
                if failures:
                    artifacts["error_message"] = failures[0]
                else:
                    artifacts["error_message"] = (
                        f"benchmark failed: returncode={proc.returncode}, "
                        f"check={fields.get('check', '')}"
                    )

        metrics["runtime_s"] = float(time.time() - start)
        return _wrap(metrics, artifacts)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _wrap(metrics: dict[str, float], artifacts: dict[str, str]):
    try:
        from openevolve.evaluation_result import EvaluationResult
    except Exception:
        return {"metrics": metrics, "artifacts": artifacts}
    return EvaluationResult(metrics=metrics, artifacts=artifacts)
