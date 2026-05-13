from __future__ import annotations

import json
import math
import argparse
import runpy
import time
import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
from numpy.random import Generator, Philox

# 候选冻结常量（2026-02-15 标定结果，建议发布前再高预算复验）
DEV_SIGMA = 0.268
TARGET_STD = 0.05
MAX_SAMPLES = 100_000
BATCH_SIZE = 10_000
MIN_ERRORS = 20
REPEATS = 3

EPSILON = 0.8
INVALID_COMBINED_SCORE = -1e18
# Re-calibrated with baseline MySampler under sigma=0.268, max_samples=10_000_000,
# 10 runs: BER uses arithmetic mean, runtime uses arithmetic mean.
R0_DEV = 7.261287772505011e-07
R0_LOG_DEV = float(math.log(R0_DEV))
T0_DEV = 10.4001037335396


def _is_repo_root(path: Path) -> bool:
    return (path / "benchmarks").is_dir() and (path / "frontier_eval").is_dir()


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _is_repo_root(parent):
            return parent
    return Path.cwd().resolve()


def _wrap(metrics: dict[str, float], artifacts: dict[str, str | bytes]):
    try:
        from openevolve.evaluation_result import EvaluationResult  # pyright: ignore[reportMissingImports]
    except ModuleNotFoundError:
        return metrics
    return EvaluationResult(metrics=metrics, artifacts=artifacts)


def _load_program_module(program_path: Path):
    if not program_path.is_file():
        raise RuntimeError(f"无法加载程序文件: {program_path}")
    namespace = runpy.run_path(str(program_path), run_name="candidate_program")
    return SimpleNamespace(**namespace)


def _resolve_program_path(program_path: str, repo_root: Path) -> Path:
    """
    Resolve candidate program path robustly.
    Priority:
    1) As provided (relative to current working directory).
    2) Relative to task root if (1) does not exist.
    """
    raw = Path(program_path).expanduser()
    if raw.is_absolute():
        return raw.resolve()

    cwd_path = (Path.cwd() / raw).resolve()
    if cwd_path.is_file():
        return cwd_path

    task_root = (
        repo_root
        / "benchmarks"
        / "WirelessChannelSimulation"
        / "HighReliableSimulation"
    )
    task_path = (task_root / raw).resolve()
    return task_path


def _normalize_result(result: Any) -> tuple[float, float, float, float, float, float]:
    """
    归一化输出到：
    errors_log, weights_log, err_ratio, total_samples, actual_std, converged(0/1)
    """
    if isinstance(result, dict):
        return (
            float(result["errors_log"]),
            float(result["weights_log"]),
            float(result.get("err_ratio", np.nan)),
            float(result.get("total_samples", np.nan)),
            float(result.get("actual_std", np.nan)),
            1.0 if bool(result.get("converged", False)) else 0.0,
        )

    if isinstance(result, (tuple, list)) and len(result) >= 6:
        return (
            float(result[0]),
            float(result[1]),
            float(result[2]),
            float(result[3]),
            float(result[4]),
            1.0 if bool(result[5]) else 0.0,
        )

    raise ValueError("simulate_variance_controlled 返回值格式不支持")


def _build_code(repo_root: Path, seed: int):
    import sys

    sys.path.insert(0, str(repo_root))
    from benchmarks.WirelessChannelSimulation.HighReliableSimulation.runtime.chase import ChaseDecoder
    from benchmarks.WirelessChannelSimulation.HighReliableSimulation.runtime.code_linear import HammingCode

    code = HammingCode(r=7, decoder="binary")
    code.rng = Generator(Philox(seed))
    code.set_decoder(ChaseDecoder(code=code, t=3))
    return code


def _run_canonical_simulation(*, code: Any, sampler: Any):
    # Use the benchmark-owned simulation loop so candidates cannot self-report
    # forged aggregate metrics through their own wrapper method.
    return code.simulate_variance_controlled(
        noise_std=DEV_SIGMA,
        target_std=TARGET_STD,
        max_samples=MAX_SAMPLES,
        sampler=sampler,
        batch_size=BATCH_SIZE,
        fix_tx=True,
        min_errors=MIN_ERRORS,
    )


def _validate_repeat_stats(
    *,
    err_rate_log: float,
    err_ratio: float,
    total_samples: float,
    actual_std: float,
) -> None:
    if not np.isfinite(err_rate_log):
        raise ValueError("err_rate_log 非有限值")
    if not np.isfinite(err_ratio) or not (0.0 <= err_ratio <= 1.0):
        raise ValueError("err_ratio 不在 [0, 1] 范围内")
    if not np.isfinite(total_samples) or total_samples <= 0:
        raise ValueError("total_samples 非法")
    if total_samples > MAX_SAMPLES:
        raise ValueError("total_samples 超过评测上限")
    if not np.isfinite(actual_std) or actual_std < 0.0:
        raise ValueError("actual_std 非法")


def evaluate(program_path: str, *, repo_root: Path | None = None):
    start = time.time()
    repo_root = _find_repo_root() if repo_root is None else repo_root.expanduser().resolve()
    program = _resolve_program_path(program_path, repo_root)

    metrics: dict[str, float] = {
        "combined_score": INVALID_COMBINED_SCORE,
        "runtime_s": 0.0,
        "error_log_ratio": float("inf"),
        "valid": 0.0,
        "timeout": 0.0,
    }
    artifacts: dict[str, str | bytes] = {}

    try:
        import sys

        sys.path.insert(0, str(repo_root))
        from benchmarks.WirelessChannelSimulation.HighReliableSimulation.runtime.sampler import SamplerBase

        try:
            module = _load_program_module(program)
        except Exception as e:
            raise RuntimeError(f"加载选手程序失败: {e}") from e
        if not hasattr(module, "MySampler"):
            raise AttributeError("提交程序中未找到类 MySampler")

        cls = module.MySampler
        if not isinstance(cls, type) or not issubclass(cls, SamplerBase):
            raise TypeError("MySampler 必须继承 SamplerBase")

        runtimes: list[float] = []
        err_logs: list[float] = []
        ratios: list[float] = []
        samples: list[float] = []
        stds: list[float] = []
        converged_flags: list[float] = []

        for rep in range(REPEATS):
            seed = rep
            code = _build_code(repo_root, seed=seed)
            try:
                sampler = cls(code=code, seed=seed)
            except Exception as e:
                raise RuntimeError(f"MySampler 初始化失败: {e}") from e
            if hasattr(sampler, "rng"):
                sampler.rng = Generator(Philox(seed))

            if not hasattr(sampler, "simulate_variance_controlled"):
                raise AttributeError("MySampler 缺少 simulate_variance_controlled 方法")

            t0 = time.time()
            try:
                result = _run_canonical_simulation(code=code, sampler=sampler)
            except Exception as e:
                raise RuntimeError(f"canonical simulate_variance_controlled 执行失败: {e}") from e
            dt = time.time() - t0

            errors_log, weights_log, err_ratio, total_samples, actual_std, converged = _normalize_result(result)
            err_rate_log = float(errors_log - weights_log)
            _validate_repeat_stats(
                err_rate_log=err_rate_log,
                err_ratio=err_ratio,
                total_samples=total_samples,
                actual_std=actual_std,
            )

            runtimes.append(float(dt))
            err_logs.append(err_rate_log)
            ratios.append(err_ratio)
            samples.append(total_samples)
            stds.append(actual_std)
            converged_flags.append(converged)

        runtime_median = float(np.median(runtimes))
        err_log_median = float(np.median(err_logs))
        err_log_ratio = float(abs(err_log_median - R0_LOG_DEV))
        std_median = float(np.median(stds))
        std_attainment_rate = float(np.mean(np.asarray(stds) <= TARGET_STD))

        valid = float(err_log_ratio < EPSILON and std_median <= TARGET_STD)
        raw_score = float(T0_DEV / (runtime_median * err_log_ratio + 1e-6))
        if valid > 0:
            score = raw_score
        else:
            score = INVALID_COMBINED_SCORE

        metrics.update(
            {
                "combined_score": score,
                "runtime_s": runtime_median,
                "error_log_ratio": err_log_ratio,
                "valid": valid,
                "timeout": 0.0,
                "err_rate_log_median": err_log_median,
                "err_ratio_median": float(np.nanmedian(ratios)),
                "actual_samples_median": float(np.nanmedian(samples)),
                "actual_std_median": std_median,
                "target_std_attainment_rate": std_attainment_rate,
                "converged_rate": float(np.mean(converged_flags)),
                "sigma": DEV_SIGMA,
                "decoder_chase_t": 3.0,
                "trusted_canonical_loop": 1.0,
            }
        )
        artifacts["dev_constants"] = json.dumps(
            {
                "sigma": DEV_SIGMA,
                "target_std": TARGET_STD,
                "max_samples": MAX_SAMPLES,
                "batch_size": BATCH_SIZE,
                "epsilon": EPSILON,
                "r0_dev": R0_DEV,
                "t0_dev": T0_DEV,
                "repeats": REPEATS,
                "scoring_note": "score requires err_rate_log close to reference and median actual_std <= target_std",
            },
            ensure_ascii=False,
            indent=2,
        )
        artifacts["per_repeat"] = json.dumps(
            {
                "runtime_s": runtimes,
                "err_rate_log": err_logs,
                "err_ratio": ratios,
                "actual_samples": samples,
                "actual_std": stds,
                "converged": converged_flags,
            },
            ensure_ascii=False,
            indent=2,
        )
    except (
        AttributeError,
        TypeError,
        ValueError,
        RuntimeError,
        ImportError,
        ModuleNotFoundError,
        KeyError,
    ) as e:
        metrics["combined_score"] = INVALID_COMBINED_SCORE
        metrics["valid"] = 0.0
        artifacts["error_message"] = str(e)
        artifacts["traceback"] = traceback.format_exc()
    finally:
        metrics["runtime_s_total"] = float(time.time() - start)

    return _wrap(metrics, artifacts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate HighReliableSimulation submission.")
    parser.add_argument("program", help="Path to candidate program file, e.g. scripts/init.py")
    parser.add_argument("--repo-root", dest="repo_root", default=None, help="Optional repository root path.")
    args = parser.parse_args()

    repo_root = None if args.repo_root is None else Path(args.repo_root).expanduser().resolve()
    result = evaluate(args.program, repo_root=repo_root)
    if isinstance(result, dict):
        metrics = result
    else:
        metrics = result.metrics
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
