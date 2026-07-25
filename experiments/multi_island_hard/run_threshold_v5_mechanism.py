#!/usr/bin/env python3
"""Run the held-out hard-Smooth/Rugged scripted topology mechanism arm."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from coral.config import CoralConfig
from experiments.multi_island import run_matrix as base
from experiments.multi_island.isolation_audit import require_sandbox_contract
from experiments.multi_island_hard import run_threshold_v4 as v4
from experiments.multi_island_hard import run_threshold_v4_canary as canary

ROOT = Path(__file__).resolve().parent
TASK_DIR = ROOT / "tasks/institutional_landscape"
CALIBRATION = ROOT / "threshold_v5_hard_smooth_calibration.json"
CONDITIONS = ("global_8", "partition_4", "multi_island_4")
SMOOTH_TASK = "smooth512_permuted_leading_ones_rep_v5"
RUGGED_TASKS = {
    64: "rugged512_k64_rep_v5",
    128: "rugged512_k128_rep_v5",
}
CONFIGS = {
    SMOOTH_TASK: "task_smooth512_permuted_leading_ones_replicated_v5.yaml",
    RUGGED_TASKS[64]: "task_rugged512_k64_replicated_v5.yaml",
    RUGGED_TASKS[128]: "task_rugged512_k128_replicated_v5.yaml",
}
RESULTS_ROOT = Path(
    "/var/tmp/coral-institutions-results/nk-threshold-v5-mechanism-v2/scripted"
)
SCRIPTED_RUNTIME = canary.SCRIPTED_RUNTIME
ENGINEERING_SMOKE = False
CONFIRMATORY_BUDGETS = (4096, 8192, 16384)

TOPOLOGIES = {
    "global_8": {"count": 1, "migration": False, "max_per_cycle": 1},
    "partition_4": {"count": 4, "migration": False, "max_per_cycle": 4},
    "multi_island_4": {"count": 4, "migration": True, "max_per_cycle": 4},
}
TASKS = {
    name: base.TaskSpec(
        name=name,
        config=TASK_DIR / config,
        cwd=TASK_DIR,
        conditions=CONDITIONS,
    )
    for name, config in CONFIGS.items()
}
BASE_BUILD_COMMAND = base.build_command


def replace_override(command: list[str], prefix: str, replacement: str) -> None:
    for index, item in enumerate(command):
        if item.startswith(prefix):
            command[index] = replacement
            return
    command.append(replacement)


def registered_selection(path: Path = CALIBRATION) -> dict[str, int]:
    data = json.loads(path.read_text())
    if not data.get("fully_registered_run"):
        raise ValueError("v5 hard-Smooth calibration is reduced")
    selected = data.get("decision", {}).get("selected_hard_anchor")
    if not isinstance(selected, dict):
        raise ValueError("v5 calibration found no hard mechanism anchor")
    k = int(selected["k"])
    budget = int(selected["budget"])
    if k not in RUGGED_TASKS or budget != 16384:
        raise ValueError("v5 calibration selected an unregistered hard anchor")
    return {"k": k, "budget": budget}


def seed_contract_errors() -> list[str]:
    errors: list[str] = []
    for task, filename in CONFIGS.items():
        try:
            config = CoralConfig.from_yaml(TASK_DIR / filename)
        except (OSError, TypeError, ValueError) as exc:
            errors.append(f"{task}: unreadable config: {exc}")
            continue
        if config.workspace.seed_path is not None:
            errors.append(f"{task}: workspace.seed_path must be null")
        source = (TASK_DIR / config.workspace.repo_path).resolve()
        try:
            candidate = v4._literal_candidate(source / "candidate.py")
        except (OSError, SyntaxError, ValueError) as exc:
            errors.append(f"{task}: invalid source candidate: {exc}")
        else:
            if len(candidate) != 512 or set(candidate) - {"0", "1"}:
                errors.append(f"{task}: source candidate is not a 512-bit literal")
        if not (source / "scripted_search.py").is_file():
            errors.append(f"{task}: scripted_search.py is missing")
    return errors


def build_command(spec: Any, condition: str, run_dir: Path) -> list[str]:
    command = BASE_BUILD_COMMAND(spec, condition, run_dir, topologies=TOPOLOGIES)
    budget = base.EXPECTED_REAL_ATTEMPTS
    if budget % 8:
        raise ValueError("scripted mechanism budget must divide evenly across eight agents")
    every = budget // 4
    topology = TOPOLOGIES[condition]
    replacements = {
        "agents.count=": "agents.count=8",
        "agents.runtime=": f"agents.runtime={SCRIPTED_RUNTIME}",
        "agents.model=": "agents.model=scripted",
        "agents.timeout=": "agents.timeout=0",
        "agents.sandbox.network=": "agents.sandbox.network=allowlist",
        "grader.parallel.max_workers=": "grader.parallel.max_workers=8",
        "islands.migration.every=": f"islands.migration.every={every}",
        "islands.migration.rank_window=": f"islands.migration.rank_window={every}",
        "islands.migration.remigration_cooldown=": (
            f"islands.migration.remigration_cooldown={every}"
        ),
        "islands.migration.max_per_cycle=": (
            f"islands.migration.max_per_cycle={topology['max_per_cycle']}"
        ),
    }
    for prefix, replacement in replacements.items():
        replace_override(command, prefix, replacement)
    heartbeat = [
        {"name": "reflect", "every": budget // 8 + 1},
        {"name": "consolidate", "every": budget + 1, "is_global": True},
        {
            "name": "pivot",
            "every": budget // 8 + 1,
            "trigger": "plateau",
        },
    ]
    visible_agents = 8 if condition == "global_8" else 2
    scripted_command = [
        "python3",
        "scripted_search.py",
        "--attempts-per-agent",
        str(budget // 8),
        "--visible-agents",
        str(visible_agents),
    ]
    command.extend(
        [
            "agents.heartbeat=" + json.dumps(heartbeat, separators=(",", ":")),
            "agents.sandbox.allowed_domains=[]",
            "islands.migration.dest_weighting=round_robin",
            "agents.runtime_options.command="
            + json.dumps(scripted_command, separators=(",", ":")),
            f"run.stop.max_real_attempts_per_agent={budget // 8}",
            f"grader.args.seed_index={v4.repetition_seed_index(run_dir)}",
        ]
    )
    return command


def argument_values(flag: str) -> list[str] | None:
    return v4._argument_values(flag)


def take_engineering_smoke() -> bool:
    global ENGINEERING_SMOKE
    if "--engineering-smoke" not in sys.argv:
        return False
    sys.argv.remove("--engineering-smoke")
    ENGINEERING_SMOKE = True
    return True


def enforce_matrix(selection: dict[str, int], *, engineering_smoke: bool) -> None:
    budget_values = argument_values("--budget")
    if engineering_smoke:
        if (
            budget_values is None
            or len(budget_values) != 1
            or int(budget_values[0]) < 32
            or int(budget_values[0]) % 8
            or int(budget_values[0]) >= CONFIRMATORY_BUDGETS[0]
        ):
            raise SystemExit(
                "--engineering-smoke requires one budget divisible by 8 in [32, 4096)"
            )
    elif (
        budget_values is None
        or len(budget_values) != 1
        or int(budget_values[0]) not in CONFIRMATORY_BUDGETS
    ):
        raise SystemExit(
            "v5 mechanism arm requires one explicit confirmatory budget: "
            + " ".join(map(str, CONFIRMATORY_BUDGETS))
        )
    allowed = (SMOOTH_TASK, RUGGED_TASKS[selection["k"]])
    requested = argument_values("--tasks")
    if requested is None:
        sys.argv.extend(["--tasks", *allowed])
    elif not requested or any(task not in allowed for task in requested):
        raise SystemExit(f"v5 mechanism arm permits only: {' '.join(allowed)}")
    conditions = argument_values("--conditions")
    if conditions is None:
        sys.argv.extend(["--conditions", *CONDITIONS])
    elif tuple(conditions) != CONDITIONS:
        raise SystemExit("v5 mechanism arm requires global, partition, and multi-island")


def main() -> int:
    try:
        require_sandbox_contract()
        errors = seed_contract_errors()
        if errors:
            raise RuntimeError("; ".join(errors))
        selection = registered_selection()
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
    engineering_smoke = take_engineering_smoke()
    enforce_matrix(selection, engineering_smoke=engineering_smoke)
    results_root = (
        RESULTS_ROOT / "engineering-smoke" if engineering_smoke else RESULTS_ROOT
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
