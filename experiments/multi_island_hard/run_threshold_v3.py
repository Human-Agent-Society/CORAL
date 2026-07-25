#!/usr/bin/env python3
"""Run the N=256 Smooth/Rugged social-learning phase matrix."""

from __future__ import annotations

import sys
from pathlib import Path

from experiments.multi_island import run_matrix as base

ROOT = Path(__file__).resolve().parent
TASK_DIR = ROOT / "tasks/institutional_landscape"
BUDGETS = (256, 512, 1024, 2048, 4096, 8192)
MODEL_API_DOMAINS = ("api.appintheloop.com",)
POLICY_ROLES = {
    "natural": ROOT / "threshold_v3_protocol.md",
    "high_diffusion": ROOT / "threshold_v3_high_diffusion_protocol.md",
}

base.TOPOLOGIES = {
    "global_8": {"count": 1, "migration": False, "max_per_cycle": 1},
    "partition_4": {"count": 4, "migration": False, "max_per_cycle": 4},
    "multi_island_2": {"count": 2, "migration": True, "max_per_cycle": 2},
    "multi_island_4": {"count": 4, "migration": True, "max_per_cycle": 4},
}
base.TASKS = {
    name: base.TaskSpec(
        name=name,
        config=TASK_DIR / config,
        cwd=TASK_DIR,
        conditions=("global_8", "partition_4", "multi_island_2", "multi_island_4"),
    )
    for name, config in {
        "smooth256_rep_v3": "task_smooth256_replicated_v3.yaml",
        "rugged256_k32_rep_v3": "task_rugged256_k32_replicated_v3.yaml",
    }.items()
}

_BASE_BUILD_COMMAND = base.build_command
_ACTIVE_POLICY = "natural"


def migration_every(budget: int) -> int:
    if budget not in BUDGETS:
        raise ValueError(f"unregistered threshold-v3 budget: {budget}")
    return budget // 4


def heartbeat_for(budget: int) -> str:
    every = max(64, budget // 8)
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
        raise ValueError("threshold v3 supports exactly eight paired seeds")
    return index


def build_command(spec, condition, run_dir):
    command = _BASE_BUILD_COMMAND(spec, condition, run_dir)
    budget = base.EXPECTED_REAL_ATTEMPTS
    every = migration_every(budget)
    topology = base.TOPOLOGIES[condition]
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


def main() -> int:
    global _ACTIVE_POLICY
    _ACTIVE_POLICY = take_policy_argument()
    if "--budget" not in sys.argv:
        raise SystemExit("threshold v3 requires one explicit registered --budget per launch")
    base.DEFAULT_RESULTS_ROOT = Path(
        f"/var/tmp/coral-institutions-results/nk-threshold-v3/{_ACTIVE_POLICY}"
    )
    previous = base.build_command
    base.build_command = build_command
    try:
        return base.main()
    finally:
        base.build_command = previous


if __name__ == "__main__":
    raise SystemExit(main())
