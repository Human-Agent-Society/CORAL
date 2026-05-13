"""Evaluator for Rayleigh Fading BER estimation task."""

from __future__ import annotations

import json
import math
import argparse
import os
import runpy
import time
import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
from numpy.random import Generator, Philox

# Frozen evaluation constants
SNR_DB = 10.0
TARGET_STD = 0.1
MAX_SAMPLES = 50_000
BATCH_SIZE = 5_000
MIN_ERRORS = 20
REPEATS = 3
NUM_BRANCHES = 4
DIVERSITY_TYPE = "MRC"
MODULATION = "BPSK"

EPSILON = 2.0  # Increased tolerance for initial submissions
# Reference values (to be calibrated with baseline solution)
R0_DEV = 1e-5  # Reference BER (adjusted for initial testing)
R0_LOG_DEV = float(math.log(R0_DEV))
T0_DEV = 10.0
ERR_RATIO_REL_TOL = 1e-6
ERR_RATIO_ABS_TOL = 1e-12
INTEGER_TOL = 1e-6


def _is_repo_root(path: Path) -> bool:
    return (path / "benchmarks").is_dir() and (path / "frontier_eval").is_dir()


def _find_repo_root() -> Path:
    env_root = (os.environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if _is_repo_root(candidate):
            return candidate

    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _is_repo_root(parent):
            return parent
    return Path.cwd().resolve()


def _task_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_import_paths(repo_root: Path) -> None:
    import sys

    for p in (repo_root, _task_root()):
        ps = str(p)
        if ps not in sys.path:
            sys.path.insert(0, ps)


def _import_sampler_base(repo_root: Path):
    _ensure_import_paths(repo_root)
    try:
        from benchmarks.CommunicationEngineering.RayleighFadingBER.runtime.sampler import SamplerBase
        return SamplerBase
    except ModuleNotFoundError:
        from runtime.sampler import SamplerBase
        return SamplerBase


def _import_channel_model(repo_root: Path):
    _ensure_import_paths(repo_root)
    try:
        from benchmarks.CommunicationEngineering.RayleighFadingBER.runtime.channel_model import RayleighFadingChannel
        return RayleighFadingChannel
    except ModuleNotFoundError:
        from runtime.channel_model import RayleighFadingChannel
        return RayleighFadingChannel


def _wrap(metrics: dict[str, float], artifacts: dict[str, str | bytes]):
    try:
        from openevolve.evaluation_result import EvaluationResult
    except ModuleNotFoundError:
        return metrics
    return EvaluationResult(metrics=metrics, artifacts=artifacts)


def _load_program_module(program_path: Path):
    if not program_path.is_file():
        raise RuntimeError(f"无法加载程序文件: {program_path}")
    namespace = runpy.run_path(str(program_path), run_name="candidate_program")
    return SimpleNamespace(**namespace)


def _resolve_program_path(program_path: str, repo_root: Path) -> Path:
    raw = Path(program_path).expanduser()
    if raw.is_absolute():
        return raw.resolve()
    cwd_path = (Path.cwd() / raw).resolve()
    if cwd_path.is_file():
        return cwd_path
    task_root = repo_root / "benchmarks" / "CommunicationEngineering" / "RayleighFadingBER"
    return (task_root / raw).resolve()


def _normalize_result(result: Any) -> dict[str, float | bool]:
    required_keys = (
        "errors_log",
        "weights_log",
        "err_ratio",
        "total_samples",
        "actual_std",
        "converged",
    )
    if isinstance(result, dict):
        missing = [key for key in required_keys if key not in result]
        if missing:
            raise ValueError(f"simulate_variance_controlled 缺少字段: {missing}")
        payload = result
    elif isinstance(result, (tuple, list)) and len(result) == 6:
        payload = {
            "errors_log": result[0],
            "weights_log": result[1],
            "err_ratio": result[2],
            "total_samples": result[3],
            "actual_std": result[4],
            "converged": result[5],
        }
    else:
        raise ValueError("simulate_variance_controlled 返回值格式不支持")

    converged = payload["converged"]
    if isinstance(converged, (np.bool_, bool)):
        converged_value = bool(converged)
    elif isinstance(converged, (int, float)) and converged in (0, 1):
        converged_value = bool(converged)
    else:
        raise ValueError("converged 必须是布尔值或 0/1")

    return {
        "errors_log": float(payload["errors_log"]),
        "weights_log": float(payload["weights_log"]),
        "err_ratio": float(payload["err_ratio"]),
        "total_samples": float(payload["total_samples"]),
        "actual_std": float(payload["actual_std"]),
        "converged": converged_value,
    }


def _validate_result(payload: dict[str, float | bool]) -> dict[str, float | bool]:
    errors_log = float(payload["errors_log"])
    weights_log = float(payload["weights_log"])
    err_ratio = float(payload["err_ratio"])
    total_samples = float(payload["total_samples"])
    actual_std = float(payload["actual_std"])
    converged = bool(payload["converged"])

    if not np.isfinite(weights_log):
        raise ValueError("weights_log 必须是有限值")
    if np.isnan(errors_log) or errors_log == float("inf"):
        raise ValueError("errors_log 必须是有限值或 -inf")
    if not np.isfinite(total_samples) or total_samples <= 0:
        raise ValueError("total_samples 必须是正数")
    rounded_samples = int(round(total_samples))
    if abs(total_samples - rounded_samples) > INTEGER_TOL:
        raise ValueError("total_samples 必须是整数")
    if rounded_samples > MAX_SAMPLES:
        raise ValueError(f"total_samples={rounded_samples} 超过 max_samples={MAX_SAMPLES}")
    if np.isnan(actual_std) or actual_std < 0.0:
        raise ValueError("actual_std 必须是非负数或 inf")
    if converged and (not np.isfinite(actual_std) or actual_std > TARGET_STD + ERR_RATIO_ABS_TOL):
        raise ValueError("converged=True 但 actual_std 未达到 target_std")

    if errors_log == float("-inf"):
        if not np.isfinite(err_ratio) or not math.isclose(err_ratio, 0.0, abs_tol=ERR_RATIO_ABS_TOL):
            raise ValueError("errors_log=-inf 时 err_ratio 必须为 0")
        if converged:
            raise ValueError("未观测到错误时不应标记 converged=True")
        derived_err_ratio = 0.0
        err_rate_log = -20.0
    else:
        if not np.isfinite(errors_log):
            raise ValueError("errors_log 必须是有限值或 -inf")
        if not np.isfinite(err_ratio) or err_ratio < 0.0 or err_ratio > 1.0 + ERR_RATIO_REL_TOL:
            raise ValueError("err_ratio 必须位于 [0, 1]")
        log_ratio = errors_log - weights_log
        if log_ratio > math.log1p(ERR_RATIO_REL_TOL):
            raise ValueError("errors_log 对应的误差权重不能超过总权重")
        derived_err_ratio = float(math.exp(log_ratio))
        if not math.isclose(
            err_ratio,
            derived_err_ratio,
            rel_tol=ERR_RATIO_REL_TOL,
            abs_tol=ERR_RATIO_ABS_TOL,
        ):
            raise ValueError(
                "err_ratio 与 errors_log/weights_log 推导出的误码率不一致"
            )
        err_rate_log = float(log_ratio)

    return {
        "errors_log": errors_log,
        "weights_log": weights_log,
        "err_ratio": derived_err_ratio,
        "total_samples": float(rounded_samples),
        "actual_std": actual_std,
        "converged": converged,
        "err_rate_log": err_rate_log,
    }


def _build_channel(repo_root: Path):
    RayleighFadingChannel = _import_channel_model(repo_root)
    return RayleighFadingChannel(num_branches=NUM_BRANCHES, sigma_h=1.0)


def evaluate(program_path: str, *, repo_root: Path | None = None):
    start = time.time()
    repo_root = _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    program = _resolve_program_path(program_path, repo_root)
    
    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "runtime_s": 0.0,
        "error_log_ratio": float("inf"),
        "valid": 0.0,
        "timeout": 0.0,
    }
    artifacts: dict[str, str | bytes] = {}
    
    try:
        SamplerBase = _import_sampler_base(repo_root)
        
        try:
            module = _load_program_module(program)
        except Exception as e:
            raise RuntimeError(f"加载选手程序失败: {e}") from e
        
        if not hasattr(module, "DeepFadeSampler"):
            raise AttributeError("提交程序中未找到类 DeepFadeSampler")
        
        cls = module.DeepFadeSampler
        if not isinstance(cls, type) or not issubclass(cls, SamplerBase):
            raise TypeError("DeepFadeSampler 必须继承 SamplerBase")
        
        runtimes: list[float] = []
        err_logs: list[float] = []
        ratios: list[float] = []
        samples: list[float] = []
        stds: list[float] = []
        converged_flags: list[float] = []
        repetition_diagnostics: list[dict[str, float | bool]] = []
        
        for rep in range(REPEATS):
            channel = _build_channel(repo_root)
            try:
                sampler = cls(channel_model=channel, seed=rep)
            except Exception as e:
                raise RuntimeError(f"DeepFadeSampler 初始化失败: {e}") from e
            
            if not hasattr(sampler, "simulate_variance_controlled"):
                raise AttributeError("DeepFadeSampler 缺少 simulate_variance_controlled 方法")
            
            t0 = time.time()
            try:
                result = sampler.simulate_variance_controlled(
                    channel_model=channel,
                    diversity_type=DIVERSITY_TYPE,
                    modulation=MODULATION,
                    snr_db=SNR_DB,
                    target_std=TARGET_STD,
                    max_samples=MAX_SAMPLES,
                    batch_size=BATCH_SIZE,
                    min_errors=MIN_ERRORS,
                )
            except Exception as e:
                raise RuntimeError(f"simulate_variance_controlled 执行失败: {e}") from e
            dt = time.time() - t0
            
            normalized = _normalize_result(result)
            validated = _validate_result(normalized)
            err_rate_log = float(validated["err_rate_log"])
            
            runtimes.append(float(dt))
            err_logs.append(err_rate_log)
            ratios.append(float(validated["err_ratio"]))
            samples.append(float(validated["total_samples"]))
            stds.append(float(validated["actual_std"]))
            converged_flags.append(1.0 if bool(validated["converged"]) else 0.0)
            repetition_diagnostics.append({
                "repeat": rep,
                "runtime_s": float(dt),
                "err_ratio": float(validated["err_ratio"]),
                "err_rate_log": err_rate_log,
                "total_samples": float(validated["total_samples"]),
                "actual_std": float(validated["actual_std"]),
                "converged": bool(validated["converged"]),
            })
        
        runtime_median = float(np.median(runtimes))
        err_log_median = float(np.median(err_logs))
        err_log_ratio = float(abs(err_log_median - R0_LOG_DEV))
        actual_std_median = float(np.nanmedian(stds))
        converged_rate = float(np.mean(converged_flags))
        variance_ok = actual_std_median <= TARGET_STD + ERR_RATIO_ABS_TOL
        convergence_ok = math.isclose(converged_rate, 1.0, abs_tol=ERR_RATIO_ABS_TOL)
        
        valid = float(err_log_ratio < EPSILON and variance_ok and convergence_ok)
        raw_score = float(T0_DEV / (runtime_median * err_log_ratio + 1e-6))
        score = raw_score if valid > 0 else 0.0
        
        metrics.update({
            "combined_score": score,
            "runtime_s": runtime_median,
            "error_log_ratio": err_log_ratio,
            "valid": valid,
            "timeout": 0.0,
            "err_rate_log_median": err_log_median,
            "err_ratio_median": float(np.nanmedian(ratios)),
            "actual_samples_median": float(np.nanmedian(samples)),
            "actual_std_median": actual_std_median,
            "converged_rate": converged_rate,
            "variance_ok": 1.0 if variance_ok else 0.0,
            "convergence_ok": 1.0 if convergence_ok else 0.0,
            "snr_db": SNR_DB,
        })
        artifacts["dev_constants"] = json.dumps({
            "snr_db": SNR_DB,
            "target_std": TARGET_STD,
            "max_samples": MAX_SAMPLES,
            "batch_size": BATCH_SIZE,
            "epsilon": EPSILON,
            "r0_dev": R0_DEV,
            "t0_dev": T0_DEV,
            "repeats": REPEATS,
        }, ensure_ascii=False, indent=2)
        artifacts["replicate_diagnostics"] = json.dumps(
            repetition_diagnostics,
            ensure_ascii=False,
            indent=2,
        )
    except (AttributeError, TypeError, ValueError, RuntimeError, ImportError, ModuleNotFoundError, KeyError) as e:
        metrics["combined_score"] = 0.0
        metrics["valid"] = 0.0
        artifacts["error_message"] = str(e)
        artifacts["traceback"] = traceback.format_exc()
    finally:
        metrics["runtime_s_total"] = float(time.time() - start)
    
    return _wrap(metrics, artifacts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Rayleigh Fading BER submission.")
    parser.add_argument("program", help="Path to candidate program file")
    parser.add_argument("--repo-root", dest="repo_root", default=None)
    parser.add_argument("--metrics-out", dest="metrics_out", default=None, help="Output metrics JSON file path.")
    args = parser.parse_args()
    
    repo_root = None if args.repo_root is None else Path(args.repo_root).expanduser().resolve()
    result = evaluate(args.program, repo_root=repo_root)
    if isinstance(result, dict):
        metrics = result
    else:
        metrics = result.metrics
    
    # Output to file if specified, otherwise stdout
    metrics_json = json.dumps(metrics, ensure_ascii=False, indent=2)
    if args.metrics_out:
        with open(args.metrics_out, 'w', encoding='utf-8') as f:
            f.write(metrics_json)
    else:
        print(metrics_json)


if __name__ == "__main__":
    main()
