#!/usr/bin/env python3
"""Audit the hard seed-bundled active-module matrix.

The primary metric is provenance-backed assembly. An exact module counts only
after a real evaluation selected that module and returned score 1.0; later
candidates receive credit only when they carry the exact tested bits. This
prevents hidden-answer recomputation from turning untested lucky bits into
"discoveries".
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import random
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
TASKDATA = ROOT / "tasks/hard_active_modular_landscape/taskdata/hard_seed_bundle.json"
TASKS = ("smooth_hard256", "rugged_hard256")
CONDITIONS = ("global", "partition", "multi_island")
REPETITIONS = 8
BLOCKS = 16
WIDTH = 16
GRADER_SRC = ROOT / "tasks/hard_active_modular_landscape/grader/src"
sys.path.insert(0, str(GRADER_SRC))
from hard_active_modular_landscape_grader.grader import (  # noqa: E402
    active_score,
    rugged_target,
    target_bits,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=Path("/var/tmp/coral-institutions-results/modular-hard-v3"))
    parser.add_argument("--budgets", type=int, nargs="+", default=[256, 512, 1024, 2048, 4096])
    parser.add_argument("--output-dir", type=Path, default=ROOT / "hard-analysis")
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def bundle() -> dict[str, Any]:
    value = load_json(TASKDATA)
    if value is None or value.get("schema_version") != 1:
        raise ValueError("invalid frozen seed bundle")
    return value


def mode_for(task: str) -> str:
    if task.startswith("smooth_"):
        return "smooth"
    if task.startswith("rugged_"):
        return "rugged"
    raise ValueError(f"unknown task {task!r}")


def parse_artifact(source: str) -> tuple[str, int]:
    tree = ast.parse(source)
    candidate: str | None = None
    active: int | None = None
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name, value = node.target.id, node.value
        else:
            raise ValueError("candidate may only contain a docstring and two assignments")
        if not isinstance(value, ast.Constant):
            raise ValueError("candidate values must be literals")
        if name == "CANDIDATE" and isinstance(value.value, str):
            if candidate is not None:
                raise ValueError("duplicate CANDIDATE")
            candidate = value.value
        elif name == "ACTIVE_MODULE" and isinstance(value.value, int):
            if active is not None:
                raise ValueError("duplicate ACTIVE_MODULE")
            active = value.value
        else:
            raise ValueError("invalid candidate assignment")
    if candidate is None or active is None or len(candidate) != BLOCKS * WIDTH or set(candidate) - {"0", "1"} or not 0 <= active < BLOCKS:
        raise ValueError("invalid hard active artifact")
    return candidate, active


def targets(task: str, seed: str) -> list[str]:
    mode = mode_for(task)
    fn = target_bits if mode == "smooth" else rugged_target
    return [fn(seed, block, WIDTH) for block in range(BLOCKS)]


def oracle_score(candidate: str, task: str, seed: str) -> tuple[float, int, int]:
    mode = mode_for(task)
    target_list = targets(task, seed)
    exact = [candidate[b * WIDTH : (b + 1) * WIDTH] == target_list[b] for b in range(BLOCKS)]
    scores = [
        active_score(candidate[b * WIDTH : (b + 1) * WIDTH], mode=mode, target=target_list[b])
        for b in range(BLOCKS)
    ]
    pairs = sum(left and right for left, right in zip(exact, exact[1:]))
    bridge = pairs / max(1, BLOCKS - 1)
    total = (sum(scores) + 0.35 * bridge) / (BLOCKS + 0.35)
    return total, sum(exact), pairs


def assembled_score(candidate: str, task: str, seed: str, known: dict[int, str]) -> tuple[float, int, int]:
    """Score only exact module bits backed by prior active evaluations."""
    mode = mode_for(task)
    target_list = targets(task, seed)
    exact: list[bool] = []
    scores: list[float] = []
    for block in range(BLOCKS):
        bits = candidate[block * WIDTH : (block + 1) * WIDTH]
        backed = known.get(block) == bits
        exact.append(backed)
        baseline = active_score("0" * WIDTH, mode=mode, target=target_list[block])
        scores.append(1.0 if backed else baseline)
    pairs = sum(left and right for left, right in zip(exact, exact[1:]))
    bridge = pairs / max(1, BLOCKS - 1)
    total = (sum(scores) + 0.35 * bridge) / (BLOCKS + 0.35)
    return total, sum(exact), pairs


def attempts(run_dir: Path) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for path in run_dir.glob(".coral/**/attempts/*.json"):
        record = load_json(path)
        if record is None or record.get("status") == "pending":
            continue
        if record.get("metadata", {}).get("budget_class", "real") != "real":
            continue
        commit = record.get("commit_hash")
        if isinstance(commit, str):
            records[commit] = record
    return sorted(records.values(), key=lambda x: (str(x.get("timestamp", "")), str(x.get("commit_hash", ""))))


def source_at(run_dir: Path, commit: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(run_dir / "repo"), "show", f"{commit}:candidate.py"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip())
    return result.stdout


def overrides(identity: dict[str, Any]) -> dict[str, str]:
    return {
        item.split("=", 1)[0]: item.split("=", 1)[1]
        for item in identity.get("command", [])
        if isinstance(item, str) and "=" in item
    }


def integrity(run_dir: Path, identity: dict[str, Any], budget: int) -> list[str]:
    errors: list[str] = []
    values = overrides(identity)
    condition = str(identity.get("condition"))
    topology = {"global": ("1", "false"), "partition": ("2", "false"), "multi_island": ("2", "true")}.get(condition)
    if topology is None:
        errors.append("unknown topology")
    else:
        if values.get("islands.count") != topology[0]:
            errors.append("wrong island count")
        if values.get("islands.migration.enabled") != topology[1]:
            errors.append("wrong migration flag")
    every = max(16, budget // 4)
    expected = {
        "agents.count": "4",
        "agents.runtime": "opencode",
        "agents.model": "mafia/glm-5.2",
        "grader.args.disable_tune": "true",
        "run.stop.max_real_attempts": str(budget),
        "grader.args.seed_index": str(int(identity.get("repetition", 1)) - 1),
        "islands.migration.every": str(every),
        "islands.migration.rank_window": str(every),
        "islands.migration.remigration_cooldown": "16",
    }
    for key, value in expected.items():
        if values.get(key) != value:
            errors.append(f"{key}={values.get(key)!r}, expected {value!r}")
    if values.get("agents.runtime_options.role_file") != str(ROOT / "hard_eval_protocol.md"):
        errors.append("wrong role protocol")
    private = run_dir / ".coral/private" / "hard_seed_bundle.json"
    if not private.is_file() or private.read_bytes() != TASKDATA.read_bytes():
        errors.append("private seed bundle mismatch")
    real = attempts(run_dir)
    if len(real) != budget:
        errors.append(f"real attempts={len(real)}, expected {budget}")
    stop = load_json(run_dir / ".coral/public/auto_stop.json") or {}
    if stop.get("reason") != "max_real_attempts":
        errors.append(f"auto-stop reason={stop.get('reason')!r}")
    migrations = list(run_dir.glob(".coral/islands/*/notes/migrations/migration_*.md"))
    if condition != "multi_island" and migrations:
        errors.append("migration notes in control")
    return errors


def collect(run_dir: Path, identity: dict[str, Any], budget: int) -> dict[str, Any]:
    task = str(identity["task"])
    seed = str(bundle()["seeds"][int(identity["repetition"]) - 1])
    parsed: list[dict[str, Any]] = []
    known: dict[int, str] = {}
    errors: list[str] = []
    for record in attempts(run_dir):
        try:
            candidate, active = parse_artifact(source_at(run_dir, str(record["commit_hash"])))
            score_value = record.get("score")
            tested = isinstance(score_value, (int, float)) and float(score_value) == 1.0
            if tested:
                known[active] = candidate[active * WIDTH : (active + 1) * WIDTH]
            assembled, exact, pairs = assembled_score(candidate, task, seed, known)
            oracle, oracle_exact, oracle_pairs = oracle_score(candidate, task, seed)
            parsed.append(
                {
                    "record": record,
                    "candidate": candidate,
                    "assembled": assembled,
                    "exact": exact,
                    "pairs": pairs,
                    "oracle": oracle,
                    "oracle_exact": oracle_exact,
                    "oracle_pairs": oracle_pairs,
                    "tested": tested,
                    "active": active,
                }
            )
        except (OSError, ValueError, SyntaxError, KeyError, TypeError):
            errors.append(str(record.get("commit_hash")))
    baseline, _, _ = assembled_score("0" * (BLOCKS * WIDTH), task, seed, {})
    best = max(parsed, key=lambda item: (item["assembled"], item["exact"])) if parsed else {
        "assembled": baseline,
        "exact": 0,
        "pairs": 0,
        "candidate": "0" * (BLOCKS * WIDTH),
        "oracle": oracle_score("0" * (BLOCKS * WIDTH), task, seed)[0],
        "oracle_exact": 0,
        "oracle_pairs": 0,
    }
    pooled_candidate = ["0"] * (BLOCKS * WIDTH)
    for block, bits in known.items():
        pooled_candidate[block * WIDTH : (block + 1) * WIDTH] = bits
    pooled_score, pooled_exact, pooled_pairs = assembled_score(
        "".join(pooled_candidate), task, seed, known
    )
    progress: list[float] = []
    current = baseline
    for item in parsed:
        current = max(current, float(item["assembled"]))
        progress.append(current)
    latest: dict[str, str] = {}
    for item in parsed:
        latest[str(item["record"].get("agent_id") or "unknown")] = str(item["candidate"])
    candidates = list(latest.values())
    distances = [
        sum(a != b for a, b in zip(left, right, strict=True)) / (BLOCKS * WIDTH)
        for index, left in enumerate(candidates)
        for right in candidates[index + 1 :]
    ]
    return {
        "task": task,
        "condition": str(identity["condition"]),
        "repetition": int(identity["repetition"]),
        "budget": budget,
        "run_dir": str(run_dir),
        "real_attempts": len(attempts(run_dir)),
        "numeric_scores": sum(item.get("score") is not None for item in attempts(run_dir)),
        "migrations": len(list(run_dir.glob(".coral/islands/*/notes/migrations/migration_*.md"))),
        "best_assembled_score": best["assembled"],
        "best_tested_blocks": best["exact"],
        "best_adjacent_pairs": best["pairs"],
        "assembled_auc": statistics.fmean(progress) if progress else baseline,
        "final_known_blocks": len(known),
        "pooled_assembled_score": pooled_score,
        "pooled_tested_blocks": pooled_exact,
        "pooled_adjacent_pairs": pooled_pairs,
        "assembly_gap": pooled_score - best["assembled"],
        "best_oracle_score": best["oracle"],
        "best_oracle_exact_blocks": best["oracle_exact"],
        "latest_diversity": statistics.fmean(distances) if distances else 0.0,
        "parse_errors": ";".join(errors),
    }


def bootstrap_difference(left: list[float], right: list[float], key: str) -> tuple[float, float]:
    if len(left) == len(right) == 1:
        return left[0] - right[0], left[0] - right[0]
    rng = random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big"))
    values = [statistics.fmean(rng.choices(left, k=len(left))) - statistics.fmean(rng.choices(right, k=len(right))) for _ in range(4000)]
    values.sort()
    return values[100], values[3900]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    root = args.results_root.resolve()
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for budget in args.budgets:
        for task in TASKS:
            for condition in CONDITIONS:
                for repetition in range(1, REPETITIONS + 1):
                    run_dir = root / f"budget-{budget}" / task / condition / f"rep-{repetition:02d}"
                    identity = load_json(run_dir / "operator-command.json")
                    if identity is None:
                        failures.append({"budget": budget, "task": task, "condition": condition, "repetition": repetition, "run_dir": str(run_dir), "reasons": ["missing run"]})
                        continue
                    reasons = integrity(run_dir, identity, budget)
                    if reasons:
                        failures.append({"budget": budget, "task": task, "condition": condition, "repetition": repetition, "run_dir": str(run_dir), "reasons": reasons})
                    else:
                        rows.append(collect(run_dir, identity, budget))
    grouped: dict[tuple[int, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(int(row["budget"]), str(row["task"]), str(row["condition"]))].append(row)
    contrasts: list[dict[str, Any]] = []
    if not failures:
        for budget in args.budgets:
            for task in TASKS:
                for reference in ("global", "partition"):
                    left = grouped[(budget, task, "multi_island")]
                    right = grouped[(budget, task, reference)]
                    for metric in (
                        "best_assembled_score",
                        "best_tested_blocks",
                        "assembled_auc",
                        "pooled_tested_blocks",
                        "assembly_gap",
                    ):
                        lv = [float(item[metric]) for item in left]
                        rv = [float(item[metric]) for item in right]
                        low, high = bootstrap_difference(lv, rv, f"{budget}:{task}:{reference}:{metric}")
                        contrasts.append({"budget": budget, "task": task, "contrast": f"multi_island_minus_{reference}", "metric": metric, "difference": statistics.fmean(lv) - statistics.fmean(rv), "ci_low": low, "ci_high": high})
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "runs.csv", rows)
    write_csv(output / "contrasts.csv", contrasts)
    audit = {"schema_version": 1, "tasks": TASKS, "conditions": CONDITIONS, "budgets": args.budgets, "repetitions": REPETITIONS, "complete_rows": len(rows), "expected_rows": len(TASKS) * len(CONDITIONS) * REPETITIONS * len(args.budgets), "integrity_failures": failures, "primary_metric": "provenance-backed assembly"}
    (output / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(f"Audited {len(rows)} complete cells; failures={len(failures)}")
    if failures and not args.allow_incomplete:
        raise SystemExit(f"Hard modular matrix incomplete; see {output / 'audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
