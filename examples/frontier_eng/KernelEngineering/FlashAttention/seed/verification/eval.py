import dataclasses
import re
import time
import os
import sys
import math
from pathlib import Path
from collections import OrderedDict

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
import torch.cuda

from baseline.utils import set_seed
try:
    from baseline.task import TestSpec
except ImportError:
    TestSpec = dict

from baseline.submission import custom_kernel
from baseline.reference import check_implementation, generate_input

WARMUP_RUNS = 10
TIMED_RUNS = 100


class PopcornOutput:
    def __init__(self, fd: int):
        self.file = os.fdopen(fd, 'w')

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


def get_test_cases(file_name: str) -> list[TestCase]:
    try:
        content = Path(file_name).read_text()
    except Exception as E:
        print(f"Could not open test file `{file_name}`: {E}", file=sys.stderr)
        exit(113)

    tests = []
    lines = content.splitlines()
    match = r"\s*([a-zA-Z_]+):\s*([a-zA-Z]+|[+-]?[0-9]+)\s*"
    for line in lines:
        if not line.strip():
            continue
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

    return tests


def warm_up(test: TestCase):
    config, Q, K, V = generate_input(**test.args)
    start = time.perf_counter()
    while time.perf_counter() - start < 0.2:
        custom_kernel((config, Q, K, V))
        torch.cuda.synchronize()


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
    variance = sum(map(lambda x: (x - avg)**2, durations))
    std = math.sqrt(variance / (runs - 1))
    err = std / math.sqrt(runs)

    return Stats(runs=runs, mean=avg, std=std, err=err, best=float(best),
                 worst=float(worst))


def run_testing(logger: PopcornOutput, tests: list[TestCase]):
    passed = True
    logger.log("test-count", len(tests))
    for idx, test in enumerate(tests):
        logger.log(f"test.{idx}.spec", test.spec)

        config, Q, K, V = generate_input(**test.args)

        torch.cuda.synchronize()
        submission_output = custom_kernel((config, Q, K, V))
        torch.cuda.synchronize()
        error = check_implementation((config, Q, K, V), submission_output)
        if error:
            logger.log(f"test.{idx}.status", "fail")
            logger.log(f"test.{idx}.error", error)
            passed = False
        else:
            logger.log(f"test.{idx}.status", "pass")

    if passed:
        logger.log("check", "pass")
        return 0
    else:
        logger.log("check", "fail")
        return 112


def benchmark(test: TestCase, recheck: bool, max_repeats: int, max_time_ns: float) -> Stats | str:
    durations = []
    config, Q, K, V = generate_input(**test.args)

    # Correctness check first
    with torch.no_grad():
        output = custom_kernel((config, Q, K, V))
        error = check_implementation((config, Q, K, V), output)
    if error:
        return error

    with torch.no_grad():
        for i in range(max_repeats):
            if recheck:
                config, Q, K, V = generate_input(**test.args)

            torch.cuda.synchronize()
            start = time.perf_counter_ns()
            output = custom_kernel((config, Q, K, V))
            torch.cuda.synchronize()
            end = time.perf_counter_ns()

            if recheck:
                error = check_implementation((config, Q, K, V), output)
                if error:
                    return error

            del output
            durations.append(end - start)

            if i > 1:
                stats = calculate_stats(durations)
                if stats.err / stats.mean < 0.01 or stats.mean * stats.runs > max_time_ns:
                    break

    return calculate_stats(durations)


def run_benchmarking(logger: PopcornOutput, tests: list[TestCase]):
    warm_up(tests[0])
    passed = True
    logger.log("benchmark-count", len(tests))
    for idx, test in enumerate(tests):
        logger.log(f"benchmark.{idx}.spec", test.spec)
        result = benchmark(test, False, 100, 10e9)
        if isinstance(result, Stats):
            for field in dataclasses.fields(Stats):
                logger.log(f"benchmark.{idx}.{field.name}", getattr(result, field.name))
        else:
            passed = False
            logger.log(f"benchmark.{idx}.status", "fail")
            logger.log(f"benchmark.{idx}.error", result)

    if passed:
        logger.log("check", "pass")
        return 0
    else:
        logger.log("check", "fail")
        return 112


def main():
    fd = os.getenv("POPCORN_FD")
    if not fd:
        return 111

    if len(sys.argv) < 3:
        return 2

    mode = sys.argv[1]
    tests = get_test_cases(sys.argv[2])

    with PopcornOutput(int(fd)) as logger:
        seed = os.getenv("POPCORN_SEED")
        seed = int(seed) if seed else 42
        set_seed(seed)

        if mode == "test":
            return run_testing(logger, tests)

        if mode == "benchmark":
            return run_benchmarking(logger, tests)

        if mode == "leaderboard":
            warm_up(tests[0])
            result = benchmark(tests[-1], True, 100, 30e9)
            if isinstance(result, Stats):
                logger.log("benchmark-count", 1)
                logger.log(f"benchmark.0.spec", tests[-1].spec)
                logger.log(f"benchmark.0.runs", result.runs)
                logger.log(f"benchmark.0.mean", result.mean)
                logger.log(f"benchmark.0.std", result.std)
                logger.log(f"benchmark.0.err", result.err)
                logger.log("check", "pass")
            else:
                logger.log("test-count", 1)
                logger.log("test.0.status", "fail")
                logger.log("test.0.error", str(result))

        else:
            return 2


if __name__ == "__main__":
    sys.exit(main())
