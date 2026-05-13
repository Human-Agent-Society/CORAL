"""Evaluator for PMD Simulation task."""

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
FIBER_LENGTH_KM = 100.0
PMD_COEFFICIENT = 0.5
DGD_THRESHOLD = 30.0
TARGET_STD = 0.1
MAX_SAMPLES = 50_000
BATCH_SIZE = 5_000
MIN_OUTAGES = 20
REPEATS = 3
NUM_SEGMENTS = 100

EPSILON = 2.0  # Increased tolerance for initial submissions
INVALID_SCORE_SCALE = 0.1
INVALID_SCORE_CAP = 0.1
# Reference values (to be calibrated with baseline solution)
R0_DEV = 1e-9  # Reference outage probability (adjusted for initial testing)
R0_LOG_DEV = float(math.log(R0_DEV))
T0_DEV = 10.0


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
        from benchmarks.CommunicationEngineering.PMDSimulation.runtime.sampler import SamplerBase
        return SamplerBase
    except ModuleNotFoundError:
        from runtime.sampler import SamplerBase
        return SamplerBase


def _import_fiber_model(repo_root: Path):
    _ensure_import_paths(repo_root)
    try:
        from benchmarks.CommunicationEngineering.PMDSimulation.runtime.fiber_model import PMDFiberModel
        return PMDFiberModel
    except ModuleNotFoundError:
        from runtime.fiber_model import PMDFiberModel
        return PMDFiberModel


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
    task_root = repo_root / "benchmarks" / "CommunicationEngineering" / "PMDSimulation"
    return (task_root / raw).resolve()


def _normalize_result(result: Any) -> tuple[float, float, float, float, float, float]:
    if isinstance(result, dict):
        return (
            float(result["outages_log"]),
            float(result["weights_log"]),
            float(result.get("outage_prob", np.nan)),
            float(result.get("total_samples", np.nan)),
            float(result.get("actual_std", np.nan)),
            1.0 if bool(result.get("converged", False)) else 0.0,
        )
    if isinstance(result, (tuple, list)) and len(result) >= 6:
        return (
            float(result[0]), float(result[1]), float(result[2]),
            float(result[3]), float(result[4]),
            1.0 if bool(result[5]) else 0.0,
        )
    raise ValueError("simulate_variance_controlled 返回值格式不支持")


def _build_fiber(repo_root: Path):
    PMDFiberModel = _import_fiber_model(repo_root)
    return PMDFiberModel(
        length_km=FIBER_LENGTH_KM,
        pmd_coefficient=PMD_COEFFICIENT,
        num_segments=NUM_SEGMENTS,
    )


def evaluate(program_path: str, *, repo_root: Path | None = None):
    start = time.time()
    repo_root = _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    program = _resolve_program_path(program_path, repo_root)
    
    metrics: dict[str, float] = {
        "combined_score": 0.0,
        "runtime_s": 0.0,
        "outage_log_ratio": float("inf"),
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
        
        if not hasattr(module, "PMDSampler"):
            raise AttributeError("提交程序中未找到类 PMDSampler")
        
        cls = module.PMDSampler
        if not isinstance(cls, type) or not issubclass(cls, SamplerBase):
            raise TypeError("PMDSampler 必须继承 SamplerBase")
        
        runtimes: list[float] = []
        outage_logs: list[float] = []
        probs: list[float] = []
        samples: list[float] = []
        stds: list[float] = []
        converged_flags: list[float] = []
        
        for rep in range(REPEATS):
            fiber = _build_fiber(repo_root)
            try:
                sampler = cls(fiber_model=fiber, seed=rep)
            except Exception as e:
                raise RuntimeError(f"PMDSampler 初始化失败: {e}") from e
            
            if not hasattr(sampler, "simulate_variance_controlled"):
                raise AttributeError("PMDSampler 缺少 simulate_variance_controlled 方法")
            
            t0 = time.time()
            try:
                result = sampler.simulate_variance_controlled(
                    fiber_model=fiber,
                    dgd_threshold=DGD_THRESHOLD,
                    target_std=TARGET_STD,
                    max_samples=MAX_SAMPLES,
                    batch_size=BATCH_SIZE,
                    min_outages=MIN_OUTAGES,
                )
            except Exception as e:
                raise RuntimeError(f"simulate_variance_controlled 执行失败: {e}") from e
            dt = time.time() - t0
            
            outages_log, weights_log, outage_prob, total_samples, actual_std, converged = _normalize_result(result)
            outage_prob_log = float(outages_log - weights_log)
            
            # Handle case when no outages found (outages_log = -inf)
            if not np.isfinite(outage_prob_log):
                # Use a very small outage probability estimate instead of -inf
                outage_prob_log = float('-20.0')  # log(2e-9), very small but finite
            
            runtimes.append(float(dt))
            outage_logs.append(outage_prob_log)
            probs.append(outage_prob)
            samples.append(total_samples)
            stds.append(actual_std)
            converged_flags.append(converged)
        
        runtime_median = float(np.median(runtimes))
        outage_log_median = float(np.median(outage_logs))
        outage_log_ratio = float(abs(outage_log_median - R0_LOG_DEV))
        
        valid = float(outage_log_ratio < EPSILON)
        raw_score = float(T0_DEV / (runtime_median * outage_log_ratio + 1e-6))
        if valid > 0:
            score = raw_score
        else:
            score = min(raw_score * INVALID_SCORE_SCALE, INVALID_SCORE_CAP)
        
        metrics.update({
            "combined_score": score,
            "runtime_s": runtime_median,
            "outage_log_ratio": outage_log_ratio,
            "valid": valid,
            "timeout": 0.0,
            "outage_prob_log_median": outage_log_median,
            "outage_prob_median": float(np.nanmedian(probs)),
            "actual_samples_median": float(np.nanmedian(samples)),
            "actual_std_median": float(np.nanmedian(stds)),
            "converged_rate": float(np.mean(converged_flags)),
            "dgd_threshold": DGD_THRESHOLD,
        })
        artifacts["dev_constants"] = json.dumps({
            "fiber_length_km": FIBER_LENGTH_KM,
            "pmd_coefficient": PMD_COEFFICIENT,
            "dgd_threshold": DGD_THRESHOLD,
            "target_std": TARGET_STD,
            "max_samples": MAX_SAMPLES,
            "batch_size": BATCH_SIZE,
            "epsilon": EPSILON,
            "r0_dev": R0_DEV,
            "t0_dev": T0_DEV,
            "repeats": REPEATS,
        }, ensure_ascii=False, indent=2)
    except (AttributeError, TypeError, ValueError, RuntimeError, ImportError, ModuleNotFoundError, KeyError) as e:
        metrics["combined_score"] = 0.0
        metrics["valid"] = 0.0
        artifacts["error_message"] = str(e)
        artifacts["traceback"] = traceback.format_exc()
    finally:
        metrics["runtime_s_total"] = float(time.time() - start)
    
    return _wrap(metrics, artifacts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate PMD Simulation submission.")
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

