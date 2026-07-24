#!/usr/bin/env python3
"""Run the pre-specified multi-island experiment matrix."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
LANDSCAPE_DIR = REPO_ROOT / "experiments/multi_island/tasks/institutional_landscape"
DEFAULT_RESULTS_ROOT = Path("/var/tmp/coral-institutions-results/matrix")
EXPECTED_REAL_ATTEMPTS = 16
TUNE_DISABLED_MARKER = "Tune mode is disabled for this controlled experiment"


@dataclass(frozen=True)
class TaskSpec:
    name: str
    config: Path
    cwd: Path
    conditions: tuple[str, ...]


TASKS = {
    "kernel": TaskSpec(
        name="kernel",
        config=REPO_ROOT / "examples/kernel_builder/task.yaml",
        cwd=REPO_ROOT,
        conditions=("global", "partition", "multi_island", "independent"),
    ),
    "smooth": TaskSpec(
        name="smooth",
        config=LANDSCAPE_DIR / "task_smooth.yaml",
        cwd=LANDSCAPE_DIR,
        conditions=("global", "partition", "multi_island"),
    ),
    "rugged": TaskSpec(
        name="rugged",
        config=LANDSCAPE_DIR / "task.yaml",
        cwd=LANDSCAPE_DIR,
        conditions=("global", "partition", "multi_island"),
    ),
}

TOPOLOGIES = {
    "global": {"count": 1, "migration": False},
    "partition": {"count": 2, "migration": False},
    "multi_island": {"count": 2, "migration": True},
    "independent": {"count": 4, "migration": False},
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--tasks", nargs="+", choices=TASKS, default=list(TASKS))
    parser.add_argument("--conditions", nargs="+", choices=TOPOLOGIES)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--max-parallel", type=int, default=2)
    parser.add_argument("--timeout-hours", type=float, default=4.0)
    parser.add_argument(
        "--budget",
        type=int,
        help="Override run.stop.max_real_attempts for every cell in this matrix",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def real_attempts(run_dir: Path) -> list[dict[str, Any]]:
    attempts: dict[str, dict[str, Any]] = {}
    for path in run_dir.glob(".coral/**/attempts/*.json"):
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("status") == "pending":
            continue
        if record.get("metadata", {}).get("budget_class", "real") != "real":
            continue
        commit_hash = record.get("commit_hash")
        if commit_hash:
            attempts[commit_hash] = record
    return list(attempts.values())


def disallowed_attempts(run_dir: Path) -> list[dict[str, Any]]:
    """Return finalized attempts that invalidate the fixed-budget protocol."""
    attempts: dict[str, dict[str, Any]] = {}
    for path in run_dir.glob(".coral/**/attempts/*.json"):
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("status") == "pending":
            continue
        budget_class = record.get("metadata", {}).get("budget_class", "real")
        violates_protocol = budget_class == "grader_error" or (
            budget_class == "tune"
            and (
                record.get("score") is not None
                or TUNE_DISABLED_MARKER not in str(record.get("feedback") or "")
            )
        )
        if not violates_protocol:
            continue
        commit_hash = record.get("commit_hash")
        if commit_hash:
            attempts[commit_hash] = record
    return list(attempts.values())


def is_complete(run_dir: Path) -> bool:
    if (run_dir / "experiment-invalid.json").is_file():
        return False
    auto_stop = run_dir / ".coral/public/auto_stop.json"
    if not auto_stop.is_file():
        return False
    try:
        state = json.loads(auto_stop.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return (
        state.get("reason") == "max_real_attempts"
        and len(real_attempts(run_dir)) == EXPECTED_REAL_ATTEMPTS
        and not disallowed_attempts(run_dir)
    )


def next_run_dir(base: Path) -> tuple[Path, bool]:
    """Return a completed directory to reuse, or a fresh retry path."""
    if is_complete(base):
        return base, True
    if not base.exists():
        return base, False
    retry = 1
    while True:
        candidate = base.with_name(f"{base.name}-retry-{retry:02d}")
        if is_complete(candidate):
            return candidate, True
        if not candidate.exists():
            return candidate, False
        retry += 1


def build_command(spec: TaskSpec, condition: str, run_dir: Path) -> list[str]:
    topology = TOPOLOGIES[condition]
    results_root = run_dir.parents[2]
    overrides = {
        "agents.count": 4,
        "agents.runtime": "opencode",
        "agents.model": "mafia/glm-5.2",
        "agents.research": False,
        "agents.runtime_options.role_file": str(
            REPO_ROOT / "experiments/multi_island/eval_protocol.md"
        ),
        "agents.sandbox.enabled": True,
        "agents.sandbox.provider": "srt",
        "agents.sandbox.network": "open",
        # The SRT policy normally denies $HOME, but this experiment stores
        # runs under /var/tmp.  Deny the enclosing results directory and let
        # SRT allow back only this cell's run slice, preventing agents from
        # inspecting pilots or earlier conditions.
        "agents.sandbox.deny_read": [str(results_root.parent)],
        "agents.stagger_seconds": 1,
        "grader.parallel.max_workers": 1,
        "grader.args.disable_tune": True,
        "islands.count": topology["count"],
        "islands.migration.enabled": topology["migration"],
        "islands.migration.every": 6,
        "islands.migration.rank_window": 6,
        "islands.migration.min_evals": 1,
        "islands.migration.max_per_cycle": 2,
        "islands.migration.remigration_cooldown": 6,
        "run.session": "local",
        "run.stop.max_real_attempts": EXPECTED_REAL_ATTEMPTS,
        "workspace.results_dir": str(results_root),
        "workspace.run_dir": str(run_dir),
    }
    if spec.name == "kernel":
        # Candidate Python is untrusted. Build its instruction stream in a
        # bubblewrap namespace with no grader taskdata, then feed JSON to the
        # private simulator in a separate process.
        overrides["grader.args.harden_candidate"] = True
        # The candidate still gets 120s.  The outer grader has an extra 30s
        # to turn a candidate timeout into a normal null-score real attempt.
        overrides["grader.timeout"] = 150
        overrides["grader.args.evaluation_timeout"] = 120
    command = ["uv", "run", "coral", "start", "-c", str(spec.config)]
    for key, value in overrides.items():
        if isinstance(value, bool):
            encoded = str(value).lower()
        elif isinstance(value, list):
            encoded = json.dumps(value, separators=(",", ":"))
        else:
            encoded = str(value)
        command.append(f"{key}={encoded}")
    return command


class Manifest:
    def __init__(self, path: Path) -> None:
        self.path = path
        if path.is_file():
            self.data = json.loads(path.read_text())
        else:
            self.data = {
                "schema_version": 1,
                "created_at": now_iso(),
                "expected_real_attempts": EXPECTED_REAL_ATTEMPTS,
                "launches": [],
            }

    def append(self, record: dict[str, Any]) -> None:
        self.data["updated_at"] = now_iso()
        self.data["launches"].append(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2) + "\n")
        os.replace(temporary, self.path)


async def terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=20)
    except TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()


async def run_one(
    *,
    spec: TaskSpec,
    condition: str,
    repetition: int,
    results_root: Path,
    timeout_seconds: float,
    semaphore: asyncio.Semaphore,
    manifest: Manifest,
    dry_run: bool,
) -> bool:
    base = results_root / spec.name / condition / f"rep-{repetition:02d}"
    run_dir, complete = next_run_dir(base)
    command = build_command(spec, condition, run_dir)
    identity = f"{spec.name}/{condition}/rep-{repetition:02d}"

    if complete:
        print(f"[skip complete] {identity}: {run_dir}", flush=True)
        return True
    if dry_run:
        print(f"[dry run] {identity}", flush=True)
        print("  " + " ".join(command), flush=True)
        return True

    async with semaphore:
        run_dir.mkdir(parents=True, exist_ok=False)
        command_record = {
            "task": spec.name,
            "condition": condition,
            "repetition": repetition,
            "run_dir": str(run_dir),
            "cwd": str(spec.cwd),
            "command": command,
            "started_at": now_iso(),
            "status": "running",
        }
        manifest.append(command_record)
        (run_dir / "operator-command.json").write_text(json.dumps(command_record, indent=2) + "\n")
        print(f"[start] {identity}: {run_dir}", flush=True)

        log_path = run_dir / "operator.log"
        with log_path.open("wb") as log:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=spec.cwd,
                stdout=log,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
            timed_out = False
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
            except TimeoutError:
                timed_out = True
                await terminate_process(process)
            except asyncio.CancelledError:
                await terminate_process(process)
                raise

        count = len(real_attempts(run_dir))
        complete = is_complete(run_dir)
        finished = {
            **command_record,
            "finished_at": now_iso(),
            "status": "complete" if complete else "failed",
            "exit_code": process.returncode,
            "timed_out": timed_out,
            "real_attempts": count,
        }
        manifest.append(finished)
        label = "complete" if complete else "FAILED"
        print(f"[{label}] {identity}: exit={process.returncode}, real={count}", flush=True)
        return complete


def ordered_cells(tasks: list[str], conditions: list[str] | None, repetitions: int):
    """Interleave task/condition cells inside each replicate."""
    for repetition in range(1, repetitions + 1):
        max_conditions = max(len(TASKS[name].conditions) for name in tasks)
        for condition_index in range(max_conditions):
            for task_name in tasks:
                spec = TASKS[task_name]
                selected = tuple(
                    c for c in spec.conditions if conditions is None or c in conditions
                )
                if condition_index < len(selected):
                    yield spec, selected[condition_index], repetition


async def async_main(args: argparse.Namespace) -> int:
    global EXPECTED_REAL_ATTEMPTS
    if args.budget is not None:
        if args.budget < 1:
            raise SystemExit("budget must be positive")
        EXPECTED_REAL_ATTEMPTS = args.budget
    if args.repetitions < 1 or args.max_parallel < 1 or args.timeout_hours <= 0:
        raise SystemExit("repetitions, max-parallel, and timeout-hours must be positive")
    results_root = args.results_root.resolve()
    if str(results_root).startswith(str(Path.home().resolve())):
        raise SystemExit(
            "SRT runs must use a results root outside $HOME; use "
            "/var/tmp/coral-institutions-results/matrix"
        )
    manifest = Manifest(results_root / "manifest.json")
    semaphore = asyncio.Semaphore(args.max_parallel)
    coroutines = [
        run_one(
            spec=spec,
            condition=condition,
            repetition=repetition,
            results_root=results_root,
            timeout_seconds=args.timeout_hours * 3600,
            semaphore=semaphore,
            manifest=manifest,
            dry_run=args.dry_run,
        )
        for spec, condition, repetition in ordered_cells(
            args.tasks, args.conditions, args.repetitions
        )
    ]
    results = await asyncio.gather(*coroutines)
    failures = len([complete for complete in results if not complete])
    print(f"Matrix finished: {len(results) - failures} complete, {failures} failed", flush=True)
    return 1 if failures else 0


def main() -> int:
    try:
        return asyncio.run(async_main(parse_args()))
    except KeyboardInterrupt:
        print("Interrupted; child process groups were terminated.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
