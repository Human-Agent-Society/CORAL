"""Reference solver for ORB (Applegate & Cook, 1991).

This implementation is allowed to use external algorithms/libraries.
Here we use OR-Tools CP-SAT through JobShopLib's ORToolsSolver wrapper.
"""

from __future__ import annotations

import argparse
import re
import time

from job_shop_lib import JobShopInstance, Schedule
from job_shop_lib.benchmarking import load_benchmark_group, load_benchmark_instance

try:
    from job_shop_lib.constraint_programming import ORToolsSolver
except Exception as exc:  # pragma: no cover - environment dependent
    ORTOOLS_IMPORT_ERROR = exc
    ORToolsSolver = None
else:
    ORTOOLS_IMPORT_ERROR = None

FAMILY_PREFIX = "orb"
FAMILY_NAME = "ORB (Applegate & Cook, 1991)"


def _natural_key(name: str) -> list[object]:
    parts = re.split(r"(\d+)", name)
    return [int(p) if p.isdigit() else p for p in parts]


def load_family_instances() -> list[JobShopInstance]:
    instances = load_benchmark_group(FAMILY_PREFIX)
    return sorted(instances, key=lambda x: _natural_key(x.name))


def solve_instance(
    instance: JobShopInstance,
    max_time_in_seconds: float = 10.0,
    log_search_progress: bool = False,
) -> Schedule:
    """Solve one instance with OR-Tools CP-SAT."""
    if ORToolsSolver is None:
        raise RuntimeError(
            "ORToolsSolver is unavailable in this environment. "
            f"Original import error: {ORTOOLS_IMPORT_ERROR}"
        )

    solver = ORToolsSolver(
        max_time_in_seconds=max_time_in_seconds,
        log_search_progress=log_search_progress,
    )
    return solver(instance)


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description=f"Run OR-Tools reference on {FAMILY_NAME} benchmark instances."
    )
    parser.add_argument(
        "--instance",
        type=str,
        default=None,
        help="Instance name. If omitted, run the first N family instances.",
    )
    parser.add_argument(
        "--max-instances",
        type=int,
        default=1,
        help="How many family instances to run when --instance is omitted.",
    )
    parser.add_argument(
        "--time-limit",
        type=float,
        default=10.0,
        help="CP-SAT time limit in seconds per instance.",
    )
    parser.add_argument(
        "--log-search-progress",
        action="store_true",
        help="Enable OR-Tools internal logging.",
    )
    args = parser.parse_args()

    if args.instance:
        instances = [load_benchmark_instance(args.instance)]
    else:
        all_instances = load_family_instances()
        instances = all_instances[: max(args.max_instances, 1)]

    for instance in instances:
        start = time.perf_counter()
        schedule = solve_instance(
            instance,
            max_time_in_seconds=args.time_limit,
            log_search_progress=args.log_search_progress,
        )
        elapsed = time.perf_counter() - start
        print(
            f"[{FAMILY_PREFIX}] {instance.name}: "
            f"makespan={schedule.makespan()} elapsed={elapsed:.4f}s "
            f"status={schedule.metadata.get('status', 'unknown')}"
        )


if __name__ == "__main__":
    _cli()
