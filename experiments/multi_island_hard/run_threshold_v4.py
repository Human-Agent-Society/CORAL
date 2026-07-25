#!/usr/bin/env python3
"""Run only the N=512 Smooth/Rugged cell selected by frozen v4 calibration."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

from coral.config import CoralConfig
from experiments.multi_island import run_matrix as base
from experiments.multi_island.isolation_audit import require_sandbox_contract

ROOT = Path(__file__).resolve().parent
TASK_DIR = ROOT / "tasks/institutional_landscape"
CALIBRATION = ROOT / "threshold_v4_scale_calibration.json"
BUDGETS = (4096, 8192, 16384)
MODEL_API_DOMAINS = ("api.appintheloop.com",)
POLICY_ROLES = {
    "natural": ROOT / "threshold_v4_protocol.md",
    "high_diffusion": ROOT / "threshold_v4_high_diffusion_protocol.md",
}
CONDITIONS = ("global_8", "partition_4", "multi_island_4")
RUGGED_TASKS = {
    k: f"rugged512_k{k}_rep_v4" for k in (16, 32, 64, 128)
}
SMOOTH_TASK = "smooth512_rep_v4"

TOPOLOGIES = {
    "global_8": {"count": 1, "migration": False, "max_per_cycle": 1},
    "partition_4": {"count": 4, "migration": False, "max_per_cycle": 4},
    "multi_island_4": {"count": 4, "migration": True, "max_per_cycle": 4},
}
_CONFIGS = {
    SMOOTH_TASK: "task_smooth512_replicated_v4.yaml",
    **{
        task: f"task_rugged512_k{k}_replicated_v4.yaml"
        for k, task in RUGGED_TASKS.items()
    },
}
TASKS = {
    name: base.TaskSpec(
        name=name,
        config=TASK_DIR / config,
        cwd=TASK_DIR,
        conditions=CONDITIONS,
    )
    for name, config in _CONFIGS.items()
}

_BASE_BUILD_COMMAND = base.build_command
_ACTIVE_POLICY = "natural"


def _literal_candidate(path: Path) -> str:
    tree = ast.parse(path.read_text(), filename=path.name)
    values = [
        statement.value.value
        for statement in tree.body
        if isinstance(statement, (ast.Assign, ast.AnnAssign))
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    ]
    if len(values) != 1:
        raise ValueError("candidate.py must contain one literal string assignment")
    return values[0]


def seed_contract_errors() -> list[str]:
    errors: list[str] = []
    for task, filename in _CONFIGS.items():
        config_path = TASK_DIR / filename
        try:
            config = CoralConfig.from_yaml(config_path)
        except (OSError, TypeError, ValueError) as exc:
            errors.append(f"{task}: unreadable config: {exc}")
            continue
        if config.workspace.seed_path is not None:
            errors.append(
                f"{task}: workspace.seed_path must be null so task-local seed/ cannot "
                "overwrite seed_v4"
            )
        source = Path(config.workspace.repo_path)
        if not source.is_absolute():
            source = (TASK_DIR / source).resolve()
        try:
            candidate = _literal_candidate(source / "candidate.py")
        except (OSError, SyntaxError, ValueError) as exc:
            errors.append(f"{task}: invalid source candidate: {exc}")
        else:
            if len(candidate) != 512 or set(candidate) - {"0", "1"}:
                errors.append(f"{task}: source candidate is not a 512-bit literal")
        if not (source / "initialize_candidate.py").is_file():
            errors.append(f"{task}: initialize_candidate.py is missing")
    return errors


def require_seed_contract() -> None:
    errors = seed_contract_errors()
    if errors:
        raise RuntimeError("threshold-v4 seed preflight failed: " + "; ".join(errors))


def registered_selection(path: Path = CALIBRATION) -> dict[str, int]:
    if not path.is_file():
        raise ValueError("v4 calibration is incomplete; no participant launch is allowed")
    data = json.loads(path.read_text())
    if not data.get("fully_registered_run"):
        raise ValueError("v4 calibration was reduced and cannot select a participant cell")
    selected = data.get("decision", {}).get("earliest_boundary_threshold")
    if not isinstance(selected, dict):
        raise ValueError("v4 calibration found no operator-robust boundary threshold")
    try:
        k = int(selected["k"])
        budget = int(selected["budget"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid v4 calibration selection") from exc
    if k not in RUGGED_TASKS or budget not in BUDGETS:
        raise ValueError("v4 calibration selected an unregistered K/budget cell")
    return {"k": k, "budget": budget}


def migration_every(budget: int) -> int:
    if budget not in BUDGETS:
        raise ValueError(f"unregistered threshold-v4 budget: {budget}")
    return budget // 4


def heartbeat_for(budget: int) -> str:
    every = max(128, budget // 8)
    return (
        f'[{{"name":"reflect","every":{every}}},'
        f'{{"name":"consolidate","every":{every * 2},"is_global":true}},'
        f'{{"name":"pivot","every":{every},"trigger":"plateau"}}]'
    )


def repetition_seed_index(run_dir: Path) -> int:
    name = run_dir.name.split("-retry-", 1)[0]
    if not name.startswith("rep-"):
        raise ValueError(f"run directory has no repetition index: {run_dir}")
    index = int(name.removeprefix("rep-")) - 1
    if not 0 <= index < 8:
        raise ValueError("threshold v4 supports exactly eight paired seeds")
    return index


def build_command(spec: Any, condition: str, run_dir: Path) -> list[str]:
    command = _BASE_BUILD_COMMAND(spec, condition, run_dir, topologies=TOPOLOGIES)
    budget = base.EXPECTED_REAL_ATTEMPTS
    every = migration_every(budget)
    topology = TOPOLOGIES[condition]
    seed_index = repetition_seed_index(run_dir)
    role = POLICY_ROLES[_ACTIVE_POLICY]
    for index, item in enumerate(command):
        if item.startswith("agents.runtime_options.role_file="):
            command[index] = f"agents.runtime_options.role_file={role}"
        elif item.startswith("agents.sandbox.network="):
            command[index] = "agents.sandbox.network=allowlist"
        elif item.startswith("islands.migration.every="):
            command[index] = f"islands.migration.every={every}"
        elif item.startswith("islands.migration.rank_window="):
            command[index] = f"islands.migration.rank_window={every}"
        elif item.startswith("islands.migration.remigration_cooldown="):
            command[index] = f"islands.migration.remigration_cooldown={every}"
        elif item.startswith("islands.migration.max_per_cycle="):
            command[index] = f"islands.migration.max_per_cycle={topology['max_per_cycle']}"
        elif item.startswith("grader.parallel.max_workers="):
            command[index] = "grader.parallel.max_workers=4"
        elif item == "agents.count=4":
            command[index] = "agents.count=8"
    command.append(f"agents.heartbeat={heartbeat_for(budget)}")
    command.append("agents.timeout=240")
    command.append('agents.sandbox.allowed_domains=["api.appintheloop.com"]')
    command.append("islands.migration.dest_weighting=round_robin")
    command.append(f"run.stop.max_real_attempts_per_agent={budget // 8}")
    command.append(f"grader.args.seed_index={seed_index}")
    return command


def take_policy_argument() -> str:
    if "--policy" not in sys.argv:
        return "natural"
    index = sys.argv.index("--policy")
    try:
        policy = sys.argv[index + 1]
    except IndexError as exc:
        raise SystemExit("--policy requires natural or high_diffusion") from exc
    del sys.argv[index : index + 2]
    if policy not in POLICY_ROLES:
        raise SystemExit("--policy requires natural or high_diffusion")
    return policy


def _argument_values(flag: str) -> list[str] | None:
    if flag not in sys.argv:
        return None
    start = sys.argv.index(flag) + 1
    values: list[str] = []
    for value in sys.argv[start:]:
        if value.startswith("--"):
            break
        values.append(value)
    return values


def enforce_selection(selection: dict[str, int]) -> None:
    budget_values = _argument_values("--budget")
    if budget_values != [str(selection["budget"])]:
        raise SystemExit(
            f"threshold v4 requires explicit --budget {selection['budget']} from calibration"
        )
    allowed_tasks = (SMOOTH_TASK, RUGGED_TASKS[selection["k"]])
    requested_tasks = _argument_values("--tasks")
    if requested_tasks is None:
        sys.argv.extend(["--tasks", *allowed_tasks])
    elif not requested_tasks or any(task not in allowed_tasks for task in requested_tasks):
        raise SystemExit(f"threshold v4 selected only these tasks: {' '.join(allowed_tasks)}")


def main() -> int:
    global _ACTIVE_POLICY
    try:
        require_sandbox_contract()
        require_seed_contract()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    _ACTIVE_POLICY = take_policy_argument()
    try:
        selection = registered_selection()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
    enforce_selection(selection)
    results_root = Path(
        f"/var/tmp/coral-institutions-results/nk-threshold-v4/{_ACTIVE_POLICY}"
    )
    previous = (
        base.TASKS,
        base.TOPOLOGIES,
        base.DEFAULT_RESULTS_ROOT,
        base.build_command,
        base.EXPECTED_REAL_ATTEMPTS,
    )
    base.TASKS = TASKS
    base.TOPOLOGIES = TOPOLOGIES
    base.DEFAULT_RESULTS_ROOT = results_root
    base.build_command = build_command
    try:
        return base.main()
    finally:
        (
            base.TASKS,
            base.TOPOLOGIES,
            base.DEFAULT_RESULTS_ROOT,
            base.build_command,
            base.EXPECTED_REAL_ATTEMPTS,
        ) = previous


if __name__ == "__main__":
    raise SystemExit(main())
