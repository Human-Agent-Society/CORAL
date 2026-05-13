import base64
import dataclasses
import multiprocessing
import re
import time
import os
import sys
import math
from pathlib import Path
from typing import Any, Optional

import torch
import torch.cuda

from ..baseline.utils import set_seed
try:
    from ..baseline.task import TestSpec
except ImportError:
    TestSpec = dict

from ..baseline.reference import check_implementation, generate_input


# ---------------------- timing helpers (NEW) ----------------------
def _now_ns() -> int:
    return time.perf_counter_ns()

def _ns_to_ms(ns: int) -> float:
    return ns / 1e6

def _safe_log(logger, key: str, value: Any):
    # Never let logging crash the run
    try:
        logger.log(key, value)
    except Exception:
        pass

class _LogSpan:
    """
    Context manager for granular timing.
    Logs:
      <prefix>.ms
    Optionally also logs:
      <prefix>.note
    """
    def __init__(self, logger, prefix: str, note: str = ""):
        self.logger = logger
        self.prefix = prefix
        self.note = note
        self.t0 = 0

    def __enter__(self):
        self.t0 = _now_ns()
        if self.note:
            _safe_log(self.logger, f"{self.prefix}.note", self.note)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        dt = _now_ns() - self.t0
        _safe_log(self.logger, f"{self.prefix}.ms", _ns_to_ms(dt))


class PopcornOutput:
    def __init__(self, fd: int):
        self.file = os.fdopen(fd, 'w')
        os.set_inheritable(fd, False)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.file.close()

    def print(self, *args, **kwargs):
        print(*args, **kwargs, file=self.file, flush=True)

    def log(self, key, value):
        self.print(f"{key}: {value}")


@dataclasses.dataclass
class TestCase:
    args: dict
    spec: str


def _combine(a: int, b: int) -> int:
    return int(a + (a + b) * (a + b + 1) // 2)


def get_test_cases(file_name: str, seed: Optional[int]) -> list[TestCase]:
    try:
        content = Path(file_name).read_text()
    except Exception as E:
        print(f"Could not open test file`{file_name}`: {E}", file=sys.stderr)
        exit(113)

    tests = []
    lines = content.splitlines()
    match = r"\s*([a-zA-Z]+):\s*([a-zA-Z]+|[+-]?[0-9]+)\s*"
    for line in lines:
        parts = line.split(";")
        case = {}
        for part in parts:
            matched = re.match(match, part)
            if not re.fullmatch(match, part):
                print(f"invalid test case: '{line}': '{part}'", file=sys.stderr)
                exit(113)
            key = matched[1]
            val = matched[2]
            try:
                val = int(val)
            except ValueError:
                pass
            case[key] = val
        tests.append(TestCase(spec=line, args=case))

    if seed is not None:
        for test in tests:
            if "seed" in test.args:
                test.args["seed"] = _combine(test.args["seed"], seed)

    return tests


@dataclasses.dataclass
class Stats:
    runs: int
    mean: float
    std: float
    err: float
    best: float
    worst: float


def calculate_stats(durations: list[int]):
    runs = len(durations)
    total = sum(durations)
    best = min(durations)
    worst = max(durations)

    avg = total / runs
    variance = sum(map(lambda x: (x - avg) ** 2, durations))
    std = math.sqrt(variance / (runs - 1))
    err = std / math.sqrt(runs)

    return Stats(runs=runs, mean=avg, std=std, err=err, best=float(best), worst=float(worst))


def _clone_data(data):
    if isinstance(data, tuple):
        return tuple(_clone_data(x) for x in data)
    elif isinstance(data, list):
        return [_clone_data(x) for x in data]
    elif isinstance(data, dict):
        return {k: _clone_data(v) for k, v in data.items()}
    elif isinstance(data, torch.Tensor):
        return data.clone()
    else:
        return data


def wrap_check_implementation(data, submission_output):
    result = check_implementation(data, submission_output)
    if isinstance(result, tuple):
        return result
    else:
        return not bool(result), result


# ---------------------- test timing plumbing (NEW, minimal) ----------------------
# These globals live inside the worker process. Parent reads them via return value.
_LAST_TEST_TIMING: dict[str, float] = {}

def _get_last_test_timing() -> dict[str, float]:
    # return a copy to avoid accidental mutation by caller
    return dict(_LAST_TEST_TIMING)


def _run_single_test(test: TestCase):
    """
    Runs a single test case. Do not call directly.
    Now also records a breakdown timing dict into a worker-global, which the parent
    can pull after pool.apply returns (via _get_last_test_timing()).
    """
    from submission import custom_kernel

    # total
    t_total0 = _now_ns()

    # generate input
    t0 = _now_ns()
    data = generate_input(**test.args)
    t_gen = _now_ns() - t0

    # clone
    t0 = _now_ns()
    data_cloned = _clone_data(data)
    t_clone = _now_ns() - t0

    # pre-sync
    t0 = _now_ns()
    torch.cuda.synchronize()
    t_sync_pre = _now_ns() - t0

    # kernel call (includes any launch overhead; NOT pure GPU time)
    t0 = _now_ns()
    submission_output = custom_kernel(data_cloned)
    t_kernel_call = _now_ns() - t0

    # post-sync (wait for GPU)
    t0 = _now_ns()
    torch.cuda.synchronize()
    t_sync_post = _now_ns() - t0

    # correctness check / wrap
    t0 = _now_ns()
    result = wrap_check_implementation(data, submission_output)
    t_check = _now_ns() - t0

    t_total = _now_ns() - t_total0

    # store breakdown in ms
    global _LAST_TEST_TIMING
    _LAST_TEST_TIMING = {
        "t_total_ms": _ns_to_ms(t_total),
        "t_gen_ms": _ns_to_ms(t_gen),
        "t_clone_ms": _ns_to_ms(t_clone),
        "t_sync_pre_ms": _ns_to_ms(t_sync_pre),
        "t_kernel_call_ms": _ns_to_ms(t_kernel_call),
        "t_sync_post_ms": _ns_to_ms(t_sync_post),
        "t_check_ms": _ns_to_ms(t_check),
    }

    return result


def run_single_test(pool: multiprocessing.Pool, test: TestCase):
    # run the test
    good, message = pool.apply(_run_single_test, (test,))
    # immediately fetch the timing dict recorded in the worker
    timing = pool.apply(_get_last_test_timing, ())
    return good, message, timing


def run_testing(logger: PopcornOutput, pool: multiprocessing.Pool, tests: list[TestCase]):
    passed = True
    logger.log("test-count", len(tests))

    for idx, test in enumerate(tests):
        logger.log(f"test.{idx}.spec", test.spec)

        with _LogSpan(logger, f"test.{idx}.total"):
            with _LogSpan(logger, f"test.{idx}.apply"):
                good, message, timing = run_single_test(pool, test)

        # (NEW) attach per-test breakdown into final result dict
        if isinstance(timing, dict) and timing:
            for k, v in timing.items():
                logger.log(f"test.{idx}.breakdown.{k}", v)

        if not good:
            logger.log(f"test.{idx}.status", "fail")
            logger.log(f"test.{idx}.error", message)
            passed = False
        else:
            logger.log(f"test.{idx}.status", "pass")
            if message:
                logger.log(f"test.{idx}.message", message)

    logger.log("check", "pass" if passed else "fail")
    return 0 if passed else 112


def _run_single_benchmark(test: TestCase, recheck: bool, max_repeats: int, max_time_ns: float):
    from submission import custom_kernel

    durations = []

    # --- setup: generate input once ---
    t0 = _now_ns()
    data = generate_input(**test.args)
    t_gen0 = _now_ns() - t0

    t0 = _now_ns()
    check_copy = _clone_data(data)
    t_clone0 = _now_ns() - t0

    # --- obligatory correctness check (once) ---
    t0 = _now_ns()
    output = custom_kernel(data)
    t_kernel0 = _now_ns() - t0

    t0 = _now_ns()
    good, message = wrap_check_implementation(check_copy, output)
    t_check0 = _now_ns() - t0
    if not good:
        return (
            f"{message} | timing(ms): gen={_ns_to_ms(t_gen0):.3f}, "
            f"clone={_ns_to_ms(t_clone0):.3f}, kernel0={_ns_to_ms(t_kernel0):.3f}, "
            f"check0={_ns_to_ms(t_check0):.3f}"
        )

    # --- timing loop ---
    bm_start_time = _now_ns()
    total_gen_ns = 0
    total_clone_ns = 0
    total_sync_ns = 0
    total_event_alloc_ns = 0
    total_event_record_ns = 0
    total_kernel_call_ns = 0
    total_elapsed_read_ns = 0
    total_check_ns = 0

    for i in range(max_repeats):
        if recheck:
            if "seed" in test.args:
                test.args["seed"] += 13

            t0 = _now_ns()
            data = generate_input(**test.args)
            total_gen_ns += (_now_ns() - t0)

            t0 = _now_ns()
            check_copy = _clone_data(data)
            total_clone_ns += (_now_ns() - t0)

        # sync + events
        t0 = _now_ns()
        torch.cuda.synchronize()
        total_sync_ns += (_now_ns() - t0)

        t0 = _now_ns()
        start_event = torch.cuda.Event(enable_timing=True)
        end_event = torch.cuda.Event(enable_timing=True)
        total_event_alloc_ns += (_now_ns() - t0)

        t0 = _now_ns()
        start_event.record()
        total_event_record_ns += (_now_ns() - t0)

        t0 = _now_ns()
        output = custom_kernel(data)
        total_kernel_call_ns += (_now_ns() - t0)

        t0 = _now_ns()
        end_event.record()
        total_event_record_ns += (_now_ns() - t0)

        t0 = _now_ns()
        torch.cuda.synchronize()
        total_sync_ns += (_now_ns() - t0)

        t0 = _now_ns()
        duration = start_event.elapsed_time(end_event) * 1e6  # ms -> ns
        total_elapsed_read_ns += (_now_ns() - t0)

        if recheck:
            t0 = _now_ns()
            good, message = check_implementation(check_copy, output)
            total_check_ns += (_now_ns() - t0)
            if not good:
                return (
                    f"{message} | loop timing(ms): gen={_ns_to_ms(total_gen_ns):.3f}, "
                    f"clone={_ns_to_ms(total_clone_ns):.3f}, sync={_ns_to_ms(total_sync_ns):.3f}, "
                    f"ev_alloc={_ns_to_ms(total_event_alloc_ns):.3f}, ev_record={_ns_to_ms(total_event_record_ns):.3f}, "
                    f"kernel_call={_ns_to_ms(total_kernel_call_ns):.3f}, elapsed_read={_ns_to_ms(total_elapsed_read_ns):.3f}, "
                    f"check={_ns_to_ms(total_check_ns):.3f}"
                )

        del output
        durations.append(duration)

        if i > 1:
            total_bm_duration = _now_ns() - bm_start_time
            stats = calculate_stats(durations)
            if (
                stats.err / stats.mean < 0.001
                or stats.mean * stats.runs > max_time_ns
                or total_bm_duration > 120e9
            ):
                break

    stats = calculate_stats(durations)
    stats.__dict__["t_gen0_ms"] = _ns_to_ms(t_gen0)
    stats.__dict__["t_clone0_ms"] = _ns_to_ms(t_clone0)
    stats.__dict__["t_kernel0_ms"] = _ns_to_ms(t_kernel0)
    stats.__dict__["t_check0_ms"] = _ns_to_ms(t_check0)
    stats.__dict__["loop_gen_ms"] = _ns_to_ms(total_gen_ns)
    stats.__dict__["loop_clone_ms"] = _ns_to_ms(total_clone_ns)
    stats.__dict__["loop_sync_ms"] = _ns_to_ms(total_sync_ns)
    stats.__dict__["loop_event_alloc_ms"] = _ns_to_ms(total_event_alloc_ns)
    stats.__dict__["loop_event_record_ms"] = _ns_to_ms(total_event_record_ns)
    stats.__dict__["loop_kernel_call_ms"] = _ns_to_ms(total_kernel_call_ns)
    stats.__dict__["loop_elapsed_read_ms"] = _ns_to_ms(total_elapsed_read_ns)
    stats.__dict__["loop_check_ms"] = _ns_to_ms(total_check_ns)
    stats.__dict__["loop_iters"] = len(durations)
    return stats


def run_single_benchmark(pool: multiprocessing.Pool, test: TestCase, recheck: bool, max_repeats: int, max_time_ns: float):
    return pool.apply(_run_single_benchmark, (test, recheck, max_repeats, max_time_ns))


def run_benchmarking(logger: PopcornOutput, pool: multiprocessing.Pool, tests: list[TestCase]):
    # warm up
    with _LogSpan(logger, "warmup.total"):
        with _LogSpan(logger, "warmup.apply"):
            run_single_benchmark(pool, tests[0], False, 100, 10e7)

    passed = True
    logger.log("benchmark-count", len(tests))

    for idx, test in enumerate(tests):
        logger.log(f"benchmark.{idx}.spec", test.spec)

        with _LogSpan(logger, f"benchmark.{idx}.total"):
            with _LogSpan(logger, f"benchmark.{idx}.apply"):
                result = run_single_benchmark(pool, test, False, 100, 10e9)

        if isinstance(result, Stats):
            # Core Stats fields
            for field in dataclasses.fields(Stats):
                logger.log(f"benchmark.{idx}.{field.name}", getattr(result, field.name))

            # Extra breakdown fields (NEW) — only if present
            extra_keys = [
                "t_gen0_ms", "t_clone0_ms", "t_kernel0_ms", "t_check0_ms",
                "loop_iters",
                "loop_gen_ms", "loop_clone_ms", "loop_sync_ms",
                "loop_event_alloc_ms", "loop_event_record_ms",
                "loop_kernel_call_ms", "loop_elapsed_read_ms", "loop_check_ms",
            ]
            for k in extra_keys:
                if k in result.__dict__:
                    logger.log(f"benchmark.{idx}.breakdown.{k}", result.__dict__[k])

        else:
            passed = False
            logger.log(f"benchmark.{idx}.status", "fail")
            logger.log(f"benchmark.{idx}.error", result)

    logger.log("check", "pass" if passed else "fail")
    return 0 if passed else 112


def run_single_profile(test: TestCase) -> str:
    from submission import custom_kernel
    from torch.profiler import profile, ProfilerActivity
    data = generate_input(**test.args)
    torch.cuda.synchronize()

    with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA]) as prof:
        submission_output = custom_kernel(_clone_data(data))
        torch.cuda.synchronize()
    return prof.key_averages().table(sort_by="self_cuda_time_total", row_limit=20)


def run_profiling(logger: PopcornOutput, tests: list[TestCase]):
    logger.log("benchmark-count", len(tests))
    for idx, test in enumerate(tests):
        logger.log(f"benchmark.{idx}.spec", test.spec)
        with _LogSpan(logger, f"profile.{idx}.total"):
            report = run_single_profile(test)
        logger.log(f"benchmark.{idx}.report", base64.b64encode(report.encode("utf-8"), b"+*").decode("utf-8"))
    logger.log("check", "pass")
    return 0


def main():
    fd = os.getenv("POPCORN_FD")
    if not fd:
        return 111

    if len(sys.argv) < 3:
        return 2

    mode = sys.argv[1]
    seed = os.getenv("POPCORN_SEED")
    os.unsetenv("POPCORN_SEED")
    seed = int(seed) if seed else None

    # ---- top-level timings (NEW) ----
    t_main0 = _now_ns()

    with PopcornOutput(int(fd)) as logger:
        _safe_log(logger, "main.mode", mode)
        _safe_log(logger, "main.argv_len", len(sys.argv))

        with _LogSpan(logger, "main.set_seed"):
            set_seed(seed or 42)

        with _LogSpan(logger, "main.get_tests"):
            tests = get_test_cases(sys.argv[2], seed)

        _safe_log(logger, "getting-tests-count", len(tests))

        # Multiprocessing setup
        with _LogSpan(logger, "main.mp_context"):
            mp_context = multiprocessing.get_context('spawn')

        with _LogSpan(logger, "main.pool_create"):
            with mp_context.Pool(1) as pool:
                _safe_log(logger, "main.pool_size", 1)

                # Dispatch by mode with per-mode total timing
                if mode == "test":
                    with _LogSpan(logger, "mode.test.total"):
                        rc = run_testing(logger, pool, tests)
                    _safe_log(logger, "main.total.ms", _ns_to_ms(_now_ns() - t_main0))
                    return rc

                if mode == "benchmark":
                    with _LogSpan(logger, "mode.benchmark.total"):
                        rc = run_benchmarking(logger, pool, tests)
                    _safe_log(logger, "main.total.ms", _ns_to_ms(_now_ns() - t_main0))
                    return rc

                if mode == "leaderboard":
                    with _LogSpan(logger, "mode.leaderboard.total"):
                        # warmup
                        with _LogSpan(logger, "leaderboard.warmup.apply"):
                            run_single_benchmark(pool, tests[0], False, 100, 1e7)

                        logger.log("benchmark-count", len(tests))
                        passed = True
                        for i in range(len(tests)):
                            logger.log(f"benchmark.{i}.spec", tests[i].spec)
                            with _LogSpan(logger, f"leaderboard.{i}.apply"):
                                result = run_single_benchmark(pool, tests[i], True, 100, 30e9)

                            if isinstance(result, Stats):
                                for field in dataclasses.fields(Stats):
                                    logger.log(f"benchmark.{i}.{field.name}", getattr(result, field.name))
                                # Extra breakdown
                                for k, v in result.__dict__.items():
                                    if k.startswith(("t_", "loop_")):
                                        logger.log(f"benchmark.{i}.breakdown.{k}", v)
                            else:
                                passed = False
                                logger.log(f"benchmark.{i}.status", "fail")
                                logger.log(f"benchmark.{i}.error", str(result))
                                break

                        logger.log("check", "pass" if passed else "fail")

                    _safe_log(logger, "main.total.ms", _ns_to_ms(_now_ns() - t_main0))
                    return 0

                elif mode == "profile":
                    with _LogSpan(logger, "mode.profile.total"):
                        rc = run_profiling(logger, tests)
                    _safe_log(logger, "main.total.ms", _ns_to_ms(_now_ns() - t_main0))
                    return rc

                else:
                    _safe_log(logger, "main.total.ms", _ns_to_ms(_now_ns() - t_main0))
                    return 2

    # Shouldn't reach here, but be safe
    return 0


if __name__ == "__main__":
    sys.exit(main())