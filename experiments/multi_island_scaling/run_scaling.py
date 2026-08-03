#!/usr/bin/env python3
"""Run the real-task global-versus-multi-island agent-count sweep."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import signal
import socket
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_DIR = Path(__file__).resolve().parent
POLY_GRADER_DIR = EXPERIMENT_DIR / "poly_grader"
POLY_PROVISION_SCRIPT = EXPERIMENT_DIR / "provision_poly_data.py"
DEFAULT_RESULTS_ROOT = Path("/var/tmp/coral-institutions-results/real-scaling-v1")
DEFAULT_COUNTS = (1, 2, 4, 8, 16, 32)
CONDITIONS = ("global", "multi_island", "sqrt_island")
PROTOCOL_TIPS = """Controlled scaling experiment protocol:
- HARD BOUNDARY: never probe hidden data or host checkouts. Do not run `find /`,
  `find ~`, `find /home`, `find /jfs`, `ls /home`, or any recursive search
  outside the current worktree and public state. Never access `.coral/private/`
  even to check it. Never search for `frozen_problem.py`, `taskdata`, or
  `submission_tests.py` by name, including with relative `find .` commands.
  A permission error is the expected boundary. A call that the runtime rejects
  before execution does not invalidate the cell because no probe occurred; do
  not retry it. Any forbidden probe that actually executes invalidates the cell.
  Continue with public task/grader files.
- Submit a serious first candidate promptly and use the available experiment window on the task.
- Use only ordinary `coral eval`; never use `coral eval --tune`.
- After feedback, spend the remaining window on the strongest correction or improvement.
- Do not spend the run only researching infrastructure. Do not spawn nested agents
  or invoke OpenCode's `task` tool; only CORAL defines the experimental population.
- Never inspect sibling runs, other islands, host paths, or `.coral/private`.
- Do not use `find` or OpenCode's glob tool anywhere in this experiment. Use
  explicit relative paths under the current worktree or `.opencode/` only.
- After migration, `.opencode/` already points at the destination island. Use
  `coral log`, `coral show`, `coral notes`, or a known `.opencode/attempts/<hash>.json`
  path; never search the run root or parent `agents/` directory for state.
"""


@dataclass(frozen=True)
class TaskSpec:
    name: str
    config: Path
    direction: str


TASKS = {
    "kernel": TaskSpec(
        name="kernel",
        config=REPO_ROOT / "examples/kernel_builder/task.yaml",
        direction="minimize",
    ),
    "polyominoes": TaskSpec(
        name="polyominoes",
        config=REPO_ROOT / "examples/frontier_cs_algo/0/task.yaml",
        direction="maximize",
    ),
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--tasks", nargs="+", choices=TASKS, default=list(TASKS))
    parser.add_argument("--conditions", nargs="+", choices=CONDITIONS, default=list(CONDITIONS))
    parser.add_argument("--agent-counts", nargs="+", type=int, default=list(DEFAULT_COUNTS))
    parser.add_argument("--per-agent-budget", type=int, default=2)
    parser.add_argument(
        "--wall-minutes",
        type=float,
        default=None,
        help="Use a fixed wall-clock stop per cell instead of a per-agent quota.",
    )
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--max-parallel", type=int, default=1)
    parser.add_argument("--timeout-hours", type=float, default=8.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def attempt_records(run_dir: Path) -> list[dict[str, Any]]:
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
        if isinstance(commit_hash, str):
            attempts[commit_hash] = record
    return list(attempts.values())


def wall_clock_stop_matches(state: dict[str, Any], expected_seconds: float) -> bool:
    """Return whether a stop marker proves the requested wall-clock budget elapsed."""
    recorded = state.get("wall_clock_seconds")
    elapsed = state.get("elapsed_wall_seconds")
    numeric = (int, float)
    return (
        state.get("reason") == "wall_clock"
        and isinstance(recorded, numeric)
        and not isinstance(recorded, bool)
        and float(recorded) == float(expected_seconds)
        and isinstance(elapsed, numeric)
        and not isinstance(elapsed, bool)
        and float(elapsed) >= float(expected_seconds)
    )


def is_complete(
    run_dir: Path,
    expected_attempts: int | None,
    wall_clock_seconds: float | None = None,
    *,
    require_operator_result: bool = True,
) -> bool:
    auto_stop = run_dir / ".coral/public/auto_stop.json"
    if not auto_stop.is_file():
        return False
    try:
        state = json.loads(auto_stop.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(state, dict):
        return False
    records = attempt_records(run_dir)
    has_score = any(record.get("score") is not None for record in records)
    if wall_clock_seconds is not None:
        result: dict[str, Any] = {}
        if require_operator_result:
            result_path = run_dir / "operator-result.json"
            if not result_path.is_file():
                return False
            try:
                result = json.loads(result_path.read_text())
            except (OSError, json.JSONDecodeError):
                return False
            if not isinstance(result, dict):
                return False
        return (
            (not require_operator_result or result.get("status") == "complete")
            and (not require_operator_result or not result.get("timed_out", False))
            and wall_clock_stop_matches(state, wall_clock_seconds)
            and has_score
        )
    # A cell whose entire quota ended in daemon/grader crashes has no
    # performance observation.  Leave it resumable so a retry can produce a
    # real score instead of silently becoming a null plotted point.
    return (
        state.get("reason") == "max_real_attempts"
        and expected_attempts is not None
        and len(records) == expected_attempts
        and has_score
    )


def next_run_dir(
    base: Path,
    expected_attempts: int | None,
    wall_clock_seconds: float | None = None,
) -> tuple[Path, bool]:
    if is_complete(base, expected_attempts, wall_clock_seconds):
        return base, True
    if not base.exists():
        return base, False
    retry = 1
    while True:
        candidate = base.with_name(f"{base.name}-retry-{retry:02d}")
        if is_complete(candidate, expected_attempts, wall_clock_seconds):
            return candidate, True
        if not candidate.exists():
            return candidate, False
        retry += 1


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def encode_override(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def island_count_for(condition: str, agent_count: int) -> int:
    """Resolve the number of islands for an experimental condition.

    ``sqrt_island`` keeps both the number of islands and the population per
    island sublinear in the total population.  Counts are rounded to the
    nearest integer and clamped to two for a genuine multi-island treatment;
    CORAL's round-robin partition keeps the resulting island populations
    balanced to within one agent.
    """
    if condition == "global" or agent_count <= 1:
        return 1
    if condition == "multi_island":
        return 2
    if condition == "sqrt_island":
        return min(agent_count, max(2, round(math.sqrt(agent_count))))
    raise ValueError(f"unknown scaling condition: {condition!r}")


def _task_field(spec: TaskSpec, field: str) -> str:
    data = yaml.safe_load(spec.config.read_text()) or {}
    return str(data.get("task", {}).get(field, "")).strip()


def build_command(
    spec: TaskSpec,
    condition: str,
    agent_count: int,
    per_agent_budget: int | None,
    results_root: Path,
    run_dir: Path,
    gateway_port: int,
    wall_clock_seconds: float | None = None,
) -> list[str]:
    total_budget = agent_count * per_agent_budget if per_agent_budget is not None else None
    island_count = island_count_for(condition, agent_count)
    multi_island = island_count > 1
    migration_every = max(2, agent_count)
    protocol = PROTOCOL_TIPS
    if wall_clock_seconds is not None:
        protocol += (
            f"\n- This cell has a fixed {wall_clock_seconds / 60:.1f}-minute wall-clock window. "
            "Keep submitting ordinary evaluations until the window closes."
        )
    else:
        protocol += "\n- Each agent has an equal real-evaluation quota for this cell."
    overrides: dict[str, Any] = {
        # Put the quota protocol before the domain description as well as in
        # tips. OpenCode reads the task description at the top of AGENTS.md,
        # so this prevents a short-budget agent from spending its only window
        # on generic orientation before it notices the experiment constraint.
        "task.description": json.dumps(
            protocol + "\nTask to optimize:\n" + _task_field(spec, "description")
        ),
        # Quote the multiline YAML scalar explicitly for OmegaConf's dotlist
        # parser. Keep the task's own tips and append the controlled protocol
        # so it appears directly in every generated AGENTS.md.
        "task.tips": json.dumps(_task_field(spec, "tips") + "\n\n" + protocol),
        "agents.count": agent_count,
        "agents.runtime": "opencode",
        "agents.model": "openai/MiniMax-M3",
        "agents.research": False,
        "agents.runtime_options.role_file": str(EXPERIMENT_DIR / "eval_protocol.md"),
        # Nested OpenCode tasks would silently change the experimental
        # population. Enforce the protocol structurally as well as in prose.
        "agents.runtime_options.disable_subagents": True,
        "agents.runtime_options.disable_file_discovery": True,
        "agents.gateway.enabled": True,
        "agents.gateway.port": gateway_port,
        "agents.gateway.config": str(EXPERIMENT_DIR / "litellm_config.yaml"),
        # Keep heartbeat actions beyond this short experiment window so the
        # measured time is spent on task search rather than documentation.
        "agents.heartbeat": [
            {
                "name": "reflect",
                "every": 100,
                "trigger": "interval",
                "is_global": False,
            },
            {
                "name": "consolidate",
                "every": 100,
                "trigger": "interval",
                "is_global": True,
            },
            {
                "name": "pivot",
                "every": 100,
                "trigger": "plateau",
                "is_global": False,
            },
            {
                "name": "lint_wiki",
                "every": 100,
                "trigger": "interval",
                "is_global": True,
            },
        ],
        # SRT supplies the OS-level read boundary that prevents an agent from
        # inspecting host checkouts or sibling runs. CORAL gives sandboxed
        # agents a proxy-routable loopback alias for its LiteLLM gateway.
        "agents.sandbox.enabled": True,
        "agents.stagger_seconds": 0,
        "grader.max_pending_per_agent": 1,
        "grader.parallel.max_workers": min(4, agent_count),
        "grader.args.disable_tune": True,
        "islands.count": island_count,
        "islands.migration.enabled": multi_island,
        "islands.migration.every": migration_every,
        "islands.migration.rank_window": migration_every,
        "islands.migration.min_evals": 1,
        # Let each source island contribute at most one migrant per cycle.
        # The old two-island condition therefore retains max_per_cycle=2,
        # while sqrt_island scales this cap with the number of islands.
        "islands.migration.max_per_cycle": min(island_count, agent_count),
        "islands.migration.remigration_cooldown": migration_every,
        "run.session": "local",
        "run.verbose": False,
        "run.ui": False,
        "workspace.results_dir": str(results_root),
        "workspace.run_dir": str(run_dir),
    }
    if wall_clock_seconds is not None:
        overrides["run.stop.wall_clock_seconds"] = wall_clock_seconds
    else:
        overrides["run.stop.max_real_attempts"] = total_budget
        overrides["run.stop.max_real_attempts_per_agent"] = per_agent_budget
    if spec.name == "kernel":
        overrides.update(
            {
                "grader.args.harden_candidate": True,
                "grader.timeout": 150,
                "grader.args.evaluation_timeout": 120,
            }
        )
    else:
        # Frontier-CS's PyPI package intentionally omits the algorithmic
        # benchmark checkout.  Use the experiment-local grader, which
        # provisions only problem #0 into the grader's private directory and
        # evaluates it with a direct local C++/checker runner.  This keeps
        # the public task worktree free of test data and works on hosts where
        # Docker's privileged go-judge service is unavailable.
        overrides.update(
            {
                "grader.entrypoint": "scaling_poly_grader.grader:Grader",
                "grader.setup": [
                    f"uv pip install -q -e {POLY_GRADER_DIR}",
                    f"python {POLY_PROVISION_SCRIPT}",
                ],
            }
        )

    command = ["uv", "run", "--no-sync", "coral", "start", "-c", str(spec.config)]
    command.extend(f"{key}={encode_override(value)}" for key, value in overrides.items())
    return command


class Manifest:
    def __init__(self, path: Path) -> None:
        self.path = path
        if path.is_file():
            self.data = json.loads(path.read_text())
        else:
            self.data = {"schema_version": 1, "created_at": now_iso(), "launches": []}

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
        await asyncio.wait_for(process.wait(), timeout=30)
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
    agent_count: int,
    repetition: int,
    per_agent_budget: int,
    wall_clock_seconds: float | None,
    results_root: Path,
    timeout_seconds: float,
    semaphore: asyncio.Semaphore,
    manifest: Manifest,
    dry_run: bool,
) -> bool:
    expected_attempts = (
        agent_count * per_agent_budget if wall_clock_seconds is None else None
    )
    base = (
        results_root / spec.name / condition / f"agents-{agent_count:02d}" / f"rep-{repetition:02d}"
    )
    run_dir, complete = next_run_dir(base, expected_attempts, wall_clock_seconds)
    identity = f"{spec.name}/{condition}/agents-{agent_count}/rep-{repetition:02d}"
    if complete:
        print(f"[skip complete] {identity}: {run_dir}", flush=True)
        return True

    if dry_run:
        command = build_command(
            spec,
            condition,
            agent_count,
            per_agent_budget,
            results_root,
            run_dir,
            gateway_port=4500,
            wall_clock_seconds=wall_clock_seconds,
        )
        print(f"[dry run] {identity}", flush=True)
        print("  " + " ".join(command), flush=True)
        return True

    async with semaphore:
        gateway_port = find_free_port()
        command = build_command(
            spec,
            condition,
            agent_count,
            per_agent_budget,
            results_root,
            run_dir,
            gateway_port,
            wall_clock_seconds=wall_clock_seconds,
        )
        run_dir.mkdir(parents=True, exist_ok=False)
        started_at = now_iso()
        record = {
            "task": spec.name,
            "direction": spec.direction,
            "condition": condition,
            "agent_count": agent_count,
            "island_count": island_count_for(condition, agent_count),
            "per_agent_budget": (
                None if wall_clock_seconds is not None else per_agent_budget
            ),
            "expected_real_attempts": expected_attempts,
            "wall_clock_seconds": wall_clock_seconds,
            "repetition": repetition,
            "run_dir": str(run_dir),
            "command": command,
            "started_at": started_at,
            "status": "running",
        }
        manifest.append(record)
        (run_dir / "operator-command.json").write_text(json.dumps(record, indent=2) + "\n")
        print(f"[start] {identity}: {run_dir}", flush=True)

        log_path = run_dir / "operator.log"
        with log_path.open("wb") as log:
            child_env = os.environ.copy()
            # The sweep is a fixed real-evaluation design.  Enforce the
            # protocol at the eval admission point as well as in prompts so
            # an agent cannot accidentally spend a cell on ``--tune``.
            child_env["CORAL_DISABLE_TUNE"] = "1"
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=REPO_ROOT,
                stdout=log,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
                env=child_env,
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

        observed_attempts = len(attempt_records(run_dir))
        complete = is_complete(
            run_dir,
            expected_attempts,
            wall_clock_seconds,
            require_operator_result=False,
        )
        finished = {
            **record,
            "finished_at": now_iso(),
            "status": "complete" if complete else "failed",
            "exit_code": process.returncode,
            "timed_out": timed_out,
            "real_attempts": observed_attempts,
        }
        manifest.append(finished)
        (run_dir / "operator-result.json").write_text(json.dumps(finished, indent=2) + "\n")
        label = "complete" if complete else "FAILED"
        print(
            f"[{label}] {identity}: exit={process.returncode}, real={observed_attempts}",
            flush=True,
        )
        return complete


def ordered_cells(args: argparse.Namespace):
    for repetition in range(1, args.repetitions + 1):
        for agent_count in args.agent_counts:
            for task_name in args.tasks:
                for condition in args.conditions:
                    # One agent cannot be partitioned. Its global run is the
                    # shared one-agent reference for both plotted curves.
                    if agent_count == 1 and condition != "global":
                        continue
                    yield TASKS[task_name], condition, agent_count, repetition


async def async_main(args: argparse.Namespace) -> int:
    if not os.environ.get("MINIMAX_API_KEY") and not args.dry_run:
        raise SystemExit("MINIMAX_API_KEY must be set in the environment")
    if any(count < 1 for count in args.agent_counts):
        raise SystemExit("all agent counts must be positive")
    if args.wall_minutes is not None and args.wall_minutes <= 0:
        raise SystemExit("wall-minutes must be positive")
    if (
        args.per_agent_budget < 1
        or args.repetitions < 1
        or args.max_parallel < 1
        or args.timeout_hours <= 0
    ):
        raise SystemExit("budgets, repetitions, max-parallel, and timeout-hours must be positive")

    results_root = args.results_root.resolve()
    if str(results_root).startswith(str(Path.home().resolve())):
        raise SystemExit("SRT experiment results must be stored outside $HOME")
    wall_clock_seconds = args.wall_minutes * 60 if args.wall_minutes is not None else None
    timeout_seconds = (
        wall_clock_seconds + 180
        if wall_clock_seconds is not None
        else args.timeout_hours * 3600
    )
    manifest = Manifest(results_root / "manifest.json")
    semaphore = asyncio.Semaphore(args.max_parallel)
    jobs = [
        run_one(
            spec=spec,
            condition=condition,
            agent_count=agent_count,
            repetition=repetition,
            per_agent_budget=args.per_agent_budget,
            wall_clock_seconds=wall_clock_seconds,
            results_root=results_root,
            timeout_seconds=timeout_seconds,
            semaphore=semaphore,
            manifest=manifest,
            dry_run=args.dry_run,
        )
        for spec, condition, agent_count, repetition in ordered_cells(args)
    ]
    results = await asyncio.gather(*jobs)
    failures = sum(not result for result in results)
    print(f"Sweep finished: {len(results) - failures} complete, {failures} failed", flush=True)
    return 1 if failures else 0


def main() -> int:
    try:
        return asyncio.run(async_main(parse_args()))
    except KeyboardInterrupt:
        print("Interrupted; active child process groups were terminated.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
