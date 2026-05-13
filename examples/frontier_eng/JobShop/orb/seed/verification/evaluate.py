"""Evaluate baseline and reference implementations on ORB (Applegate & Cook, 1991).

Baseline is pure-python and independent from `job_shop_lib`.
Reference uses `job_shop_lib` + OR-Tools.
"""

from __future__ import annotations

import argparse
import importlib.util
import numbers
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType


FAMILY_PREFIX = "orb"
FAMILY_NAME = "ORB (Applegate & Cook, 1991)"


@dataclass
class InstanceResult:
    name: str
    optimum: int | None
    lower_bound: int | None
    upper_bound: int | None
    baseline_makespan: int | None
    baseline_valid: bool
    baseline_note: str | None
    baseline_elapsed_s: float
    reference_makespan: int | None
    reference_elapsed_s: float | None
    reference_error: str | None


@dataclass
class ScheduleValidation:
    actual_makespan: int
    note: str | None


def _load_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _coerce_int(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer, got bool")
    try:
        coerced = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if isinstance(value, numbers.Real) and not isinstance(value, numbers.Integral):
        if float(value) != float(coerced):
            raise ValueError(f"{field} must be an integer")
    return coerced


def _validate_baseline_schedule(
    instance: dict,
    result: object,
) -> ScheduleValidation:
    if not isinstance(result, dict):
        raise ValueError("solver output must be a dict")

    machine_schedules = result.get("machine_schedules")
    if not isinstance(machine_schedules, list):
        raise ValueError("solver output must include machine_schedules as a list")

    durations: list[list[int]] = instance["duration_matrix"]
    machines: list[list[int]] = instance["machines_matrix"]
    num_jobs = len(durations)
    num_machines = (
        max((machine_id for row in machines for machine_id in row), default=-1) + 1
    )
    expected_operation_count = sum(len(job) for job in durations)

    if len(machine_schedules) != num_machines:
        raise ValueError(
            f"machine_schedules has {len(machine_schedules)} machines, "
            f"expected {num_machines}"
        )

    seen_operations: set[tuple[int, int]] = set()
    operation_starts: dict[tuple[int, int], int] = {}
    operation_ends: dict[tuple[int, int], int] = {}
    actual_makespan = 0

    for machine_id, machine_ops in enumerate(machine_schedules):
        if not isinstance(machine_ops, list):
            raise ValueError(f"machine_schedules[{machine_id}] must be a list")

        intervals: list[tuple[int, int, int, int]] = []
        for op_pos, operation in enumerate(machine_ops):
            if not isinstance(operation, dict):
                raise ValueError(
                    f"machine_schedules[{machine_id}][{op_pos}] must be a dict"
                )
            for field in ("job_id", "operation_index", "start_time", "end_time"):
                if field not in operation:
                    raise ValueError(
                        f"machine_schedules[{machine_id}][{op_pos}] is missing {field}"
                    )

            job_id = _coerce_int(
                operation["job_id"],
                f"machine_schedules[{machine_id}][{op_pos}].job_id",
            )
            op_idx = _coerce_int(
                operation["operation_index"],
                f"machine_schedules[{machine_id}][{op_pos}].operation_index",
            )
            start_time = _coerce_int(
                operation["start_time"],
                f"machine_schedules[{machine_id}][{op_pos}].start_time",
            )
            end_time = _coerce_int(
                operation["end_time"],
                f"machine_schedules[{machine_id}][{op_pos}].end_time",
            )

            if job_id < 0 or job_id >= num_jobs:
                raise ValueError(
                    f"machine_schedules[{machine_id}][{op_pos}] references "
                    f"unknown job {job_id}"
                )
            if op_idx < 0 or op_idx >= len(durations[job_id]):
                raise ValueError(
                    f"machine_schedules[{machine_id}][{op_pos}] references "
                    f"unknown operation {op_idx} for job {job_id}"
                )
            if start_time < 0:
                raise ValueError(
                    f"job {job_id} op {op_idx} has negative start_time {start_time}"
                )
            if end_time < start_time:
                raise ValueError(
                    f"job {job_id} op {op_idx} ends before it starts"
                )

            expected_machine = machines[job_id][op_idx]
            if expected_machine != machine_id:
                raise ValueError(
                    f"job {job_id} op {op_idx} scheduled on machine {machine_id}, "
                    f"expected machine {expected_machine}"
                )

            expected_duration = durations[job_id][op_idx]
            actual_duration = end_time - start_time
            if actual_duration != expected_duration:
                raise ValueError(
                    f"job {job_id} op {op_idx} duration {actual_duration} does not "
                    f"match expected {expected_duration}"
                )

            if "duration" in operation and operation["duration"] is not None:
                duration = _coerce_int(
                    operation["duration"],
                    f"machine_schedules[{machine_id}][{op_pos}].duration",
                )
                if duration != expected_duration:
                    raise ValueError(
                        f"job {job_id} op {op_idx} reported duration {duration} "
                        f"does not match expected {expected_duration}"
                    )

            op_key = (job_id, op_idx)
            if op_key in seen_operations:
                raise ValueError(
                    f"job {job_id} op {op_idx} appears more than once in the schedule"
                )

            seen_operations.add(op_key)
            operation_starts[op_key] = start_time
            operation_ends[op_key] = end_time
            intervals.append((start_time, end_time, job_id, op_idx))
            actual_makespan = max(actual_makespan, end_time)

        prev_end: int | None = None
        prev_op: tuple[int, int] | None = None
        for start_time, end_time, job_id, op_idx in sorted(intervals):
            if prev_end is not None and start_time < prev_end and prev_op is not None:
                raise ValueError(
                    f"machine {machine_id} overlaps job {prev_op[0]} op {prev_op[1]} "
                    f"with job {job_id} op {op_idx}"
                )
            prev_end = end_time
            prev_op = (job_id, op_idx)

    if len(seen_operations) != expected_operation_count:
        missing = [
            f"job {job_id} op {op_idx}"
            for job_id, job in enumerate(durations)
            for op_idx in range(len(job))
            if (job_id, op_idx) not in seen_operations
        ]
        missing_preview = ", ".join(missing[:5])
        if len(missing) > 5:
            missing_preview += ", ..."
        raise ValueError(
            f"schedule is missing {len(missing)} operations: {missing_preview}"
        )

    for job_id, job in enumerate(durations):
        for op_idx in range(len(job) - 1):
            current_op = (job_id, op_idx)
            next_op = (job_id, op_idx + 1)
            if operation_starts[next_op] < operation_ends[current_op]:
                raise ValueError(
                    f"job {job_id} violates precedence between op {op_idx} "
                    f"and op {op_idx + 1}"
                )

    if "makespan" not in result:
        raise ValueError("solver output must include makespan")

    reported_makespan = _coerce_int(result["makespan"], "makespan")
    if reported_makespan != actual_makespan:
        raise ValueError(
            f"reported makespan {reported_makespan} does not match recomputed "
            f"{actual_makespan}"
        )

    return ScheduleValidation(actual_makespan=actual_makespan, note=None)


def _score(target: int | None, makespan: int | None) -> float | None:
    if target is None or makespan is None or makespan <= 0:
        return None
    return min(100.0, 100.0 * float(target) / float(makespan))


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return statistics.fmean(values)


def _fmt_int(value: int | None) -> str:
    return "-" if value is None else str(value)


def _fmt_float(value: float | None, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _select_instances(
    all_instances: list[dict],
    names: list[str] | None,
    max_instances: int | None,
) -> list[dict]:
    selected = all_instances
    if names:
        by_name = {ins["name"]: ins for ins in selected}
        missing = [name for name in names if name not in by_name]
        if missing:
            raise ValueError(
                f"Unknown instance(s): {missing}. "
                f"Known prefix={FAMILY_PREFIX}."
            )
        selected = [by_name[name] for name in names]
    if max_instances is not None:
        selected = selected[: max(max_instances, 0)]
    return selected


def evaluate_instances(
    instances: list[dict],
    reference_time_limit: float,
    baseline_mod: ModuleType,
    reference_mod: ModuleType,
) -> list[InstanceResult]:
    results: list[InstanceResult] = []

    reference_map = {
        ins.name: ins
        for ins in reference_mod.load_family_instances()
    }

    for instance in instances:
        meta = instance["metadata"]
        optimum = meta.get("optimum")
        lower_bound = meta.get("lower_bound")
        upper_bound = meta.get("upper_bound")

        baseline_makespan: int | None = None
        baseline_valid = False
        baseline_note: str | None = None
        start = time.perf_counter()
        try:
            baseline_result = baseline_mod.solve_instance(instance)
            validation = _validate_baseline_schedule(instance, baseline_result)
            baseline_makespan = validation.actual_makespan
            baseline_valid = True
            baseline_note = validation.note
        except Exception as exc:
            baseline_note = str(exc)
        baseline_elapsed = time.perf_counter() - start

        reference_makespan: int | None = None
        reference_elapsed: float | None = None
        reference_error: str | None = None

        try:
            ref_instance = reference_map[instance["name"]]
            start = time.perf_counter()
            ref_schedule = reference_mod.solve_instance(
                ref_instance,
                max_time_in_seconds=reference_time_limit,
            )
            reference_elapsed = time.perf_counter() - start
            reference_makespan = ref_schedule.makespan()
        except Exception as exc:  # pragma: no cover - environment dependent
            reference_error = str(exc)

        results.append(
            InstanceResult(
                name=instance["name"],
                optimum=optimum,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                baseline_makespan=baseline_makespan,
                baseline_valid=baseline_valid,
                baseline_note=baseline_note,
                baseline_elapsed_s=baseline_elapsed,
                reference_makespan=reference_makespan,
                reference_elapsed_s=reference_elapsed,
                reference_error=reference_error,
            )
        )

    return results


def print_report(results: list[InstanceResult]) -> None:
    if not results:
        print("No instances selected.")
        return

    print(f"Family: {FAMILY_NAME} ({FAMILY_PREFIX})")
    print(
        "Columns: instance | baseline_ok | baseline_ms | reference_ms | optimum | "
        "lower_bound | best_score(b/r) | lb_score(b/r)"
    )

    baseline_best_scores: list[float] = []
    reference_best_scores: list[float] = []
    baseline_lb_scores: list[float] = []
    reference_lb_scores: list[float] = []
    baseline_opt_gaps: list[float] = []
    reference_opt_gaps: list[float] = []

    for row in results:
        target = row.optimum if row.optimum is not None else row.upper_bound

        b_best = _score(target, row.baseline_makespan)
        r_best = _score(target, row.reference_makespan)
        b_lb = _score(row.lower_bound, row.baseline_makespan)
        r_lb = _score(row.lower_bound, row.reference_makespan)

        if b_best is not None:
            baseline_best_scores.append(b_best)
        if r_best is not None:
            reference_best_scores.append(r_best)
        if b_lb is not None:
            baseline_lb_scores.append(b_lb)
        if r_lb is not None:
            reference_lb_scores.append(r_lb)

        if row.optimum is not None and row.baseline_makespan is not None:
            baseline_opt_gaps.append(
                100.0 * (row.baseline_makespan - row.optimum) / row.optimum
            )
        if row.optimum is not None:
            if row.reference_makespan is not None:
                reference_opt_gaps.append(
                    100.0 * (row.reference_makespan - row.optimum) / row.optimum
                )

        print(
            f"{row.name:8} | "
            f"{('valid' if row.baseline_valid else 'invalid'):11} | "
            f"{_fmt_int(row.baseline_makespan):11} | "
            f"{_fmt_int(row.reference_makespan):11} | "
            f"{_fmt_int(row.optimum):7} | "
            f"{_fmt_int(row.lower_bound):11} | "
            f"{_fmt_float(b_best):>6}/{_fmt_float(r_best):<6} | "
            f"{_fmt_float(b_lb):>6}/{_fmt_float(r_lb):<6}"
        )

    baseline_diagnostics = [r for r in results if r.baseline_note is not None]
    baseline_invalid = [r for r in results if not r.baseline_valid]
    reference_failures = [r for r in results if r.reference_error is not None]

    print("\nSummary")
    print(f"- instances: {len(results)}")
    print(f"- invalid baseline schedules: {len(baseline_invalid)}")
    print(f"- reference failures: {len(reference_failures)}")
    print(
        f"- avg baseline runtime (s): "
        f"{_fmt_float(_mean([r.baseline_elapsed_s for r in results]), 4)}"
    )
    print(
        f"- avg reference runtime (s): "
        f"{_fmt_float(_mean([r.reference_elapsed_s for r in results if r.reference_elapsed_s is not None]), 4)}"
    )
    print(
        f"- avg best-known score   (baseline/reference): "
        f"{_fmt_float(_mean(baseline_best_scores))} / "
        f"{_fmt_float(_mean(reference_best_scores))}"
    )
    print(
        f"- avg lower-bound score  (baseline/reference): "
        f"{_fmt_float(_mean(baseline_lb_scores))} / "
        f"{_fmt_float(_mean(reference_lb_scores))}"
    )
    print(
        f"- avg optimality gap %   (baseline/reference, known optimum only): "
        f"{_fmt_float(_mean(baseline_opt_gaps))} / "
        f"{_fmt_float(_mean(reference_opt_gaps))}"
    )
    print("- theoretical score ceiling under score_lb formula: 100.00")

    if baseline_diagnostics:
        print("\nBaseline validation notes:")
        for row in baseline_diagnostics[:5]:
            print(f"- {row.name}: {row.baseline_note}")
        if len(baseline_diagnostics) > 5:
            print(f"- ... {len(baseline_diagnostics) - 5} more")

    if reference_failures:
        print("\nReference solver errors:")
        for err in reference_failures[:5]:
            print(f"- {err.name}: {err.reference_error}")


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description=(
            f"Evaluate baseline and reference implementations for "
            f"{FAMILY_NAME} ({FAMILY_PREFIX})."
        )
    )
    parser.add_argument(
        "--instances",
        nargs="*",
        default=None,
        help="Optional explicit instance names.",
    )
    parser.add_argument(
        "--max-instances",
        type=int,
        default=None,
        help="Evaluate only the first N selected instances.",
    )
    parser.add_argument(
        "--reference-time-limit",
        type=float,
        default=10.0,
        help="Time limit in seconds per instance for reference solver.",
    )
    args = parser.parse_args()

    family_dir = Path(__file__).resolve().parents[1]
    baseline_mod = _load_module(
        f"baseline_{FAMILY_PREFIX}",
        family_dir / "baseline" / "init.py",
    )
    reference_mod = _load_module(
        f"reference_{FAMILY_PREFIX}",
        family_dir / "verification" / "reference.py",
    )

    all_instances = baseline_mod.load_family_instances()
    selected = _select_instances(all_instances, args.instances, args.max_instances)
    results = evaluate_instances(
        selected,
        args.reference_time_limit,
        baseline_mod,
        reference_mod,
    )
    print_report(results)


if __name__ == "__main__":
    _cli()
