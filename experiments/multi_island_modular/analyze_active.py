#!/usr/bin/env python3
"""Audit the active-module confirmatory matrix."""

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
TASKDATA = ROOT / "tasks/active_modular_landscape/taskdata"
TASKS = ("smooth_active128", "rugged_active128")
CONDITIONS = ("global", "partition", "multi_island")
REPETITIONS = 8
GRADER_SRC = ROOT / "tasks/active_modular_landscape/grader/src"

sys.path.insert(0, str(GRADER_SRC))
from active_modular_landscape_grader.grader import (  # noqa: E402
    active_score,
    rugged_target,
    target_bits,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=Path("/var/tmp/coral-institutions-results/modular-active-v2"))
    parser.add_argument("--budgets", type=int, nargs="+", default=[64, 128, 256, 512])
    parser.add_argument("--output-dir", type=Path, default=ROOT / "active-analysis")
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def config(task: str) -> dict[str, Any]:
    return load_json(TASKDATA / f"{task}.json") or {}


def parse_artifact(source: str, n: int, blocks: int) -> tuple[str, int]:
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
            raise ValueError("unexpected candidate statement")
        if not isinstance(value, ast.Constant):
            raise ValueError("candidate values must be literals")
        if name == "CANDIDATE" and isinstance(value.value, str):
            candidate = value.value
        elif name == "ACTIVE_MODULE" and isinstance(value.value, int):
            active = value.value
        else:
            raise ValueError("invalid candidate assignment")
    if candidate is None or active is None or len(candidate) != n or set(candidate) - {"0", "1"} or not 0 <= active < blocks:
        raise ValueError("invalid active artifact")
    return candidate, active


def artifact_score(candidate: str, task: str) -> tuple[float, int, int]:
    item = config(task)
    blocks, width = int(item["blocks"]), int(item["block_width"])
    mode, seed = str(item["mode"]), str(item["seed"])
    scores: list[float] = []
    exact: list[bool] = []
    for block in range(blocks):
        bits = candidate[block * width : (block + 1) * width]
        target = target_bits(seed, block, width) if mode == "smooth" else rugged_target(seed, block, width)
        scores.append(active_score(bits, mode=mode, target=target))
        exact.append(bits == target)
    pairs = sum(left and right for left, right in zip(exact, exact[1:]))
    bridge = pairs / max(1, blocks - 1)
    total = (sum(scores) + 0.35 * bridge) / (blocks + 0.35)
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
    every = max(8, budget // 4)
    expected = {
        "agents.count": "4",
        "agents.runtime": "opencode",
        "agents.model": "mafia/glm-5.2",
        "grader.args.disable_tune": "true",
        "run.stop.max_real_attempts": str(budget),
        "islands.migration.every": str(every),
        "islands.migration.rank_window": str(every),
        "islands.migration.remigration_cooldown": "8",
    }
    for key, value in expected.items():
        if values.get(key) != value:
            errors.append(f"{key}={values.get(key)!r}, expected {value!r}")
    if values.get("agents.runtime_options.role_file") != str(ROOT / "eval_protocol.md"):
        errors.append("wrong role protocol")
    task = str(identity.get("task"))
    private = run_dir / ".coral/private" / f"{task}.json"
    frozen = TASKDATA / f"{task}.json"
    if not private.is_file() or not frozen.is_file() or private.read_bytes() != frozen.read_bytes():
        errors.append("private taskdata mismatch")
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
    item = config(task)
    n = int(item["blocks"]) * int(item["block_width"])
    parsed: list[tuple[dict[str, Any], str, float, int, int]] = []
    parse_errors: list[str] = []
    for record in attempts(run_dir):
        try:
            candidate, active = parse_artifact(source_at(run_dir, str(record["commit_hash"])), n, int(item["blocks"]))
            value, exact, pairs = artifact_score(candidate, task)
            parsed.append((record, candidate, value, exact, pairs))
        except (OSError, ValueError, SyntaxError, KeyError, TypeError):
            parse_errors.append(str(record.get("commit_hash")))
    baseline = "0" * n
    base_score, base_exact, base_pairs = artifact_score(baseline, task)
    best = max(parsed, key=lambda x: x[2]) if parsed else ({}, baseline, base_score, base_exact, base_pairs)
    progress: list[float] = []
    current = base_score
    for _record, _candidate, score, _exact, _pairs in parsed:
        current = max(current, score)
        progress.append(current)
    latest: dict[str, str] = {}
    for record, candidate, _score, _exact, _pairs in parsed:
        latest[str(record.get("agent_id") or "unknown")] = candidate
    distances = [
        sum(a != b for a, b in zip(left, right, strict=True)) / n
        for index, left in enumerate(latest.values())
        for right in list(latest.values())[index + 1 :]
    ]
    return {
        "task": task,
        "condition": str(identity["condition"]),
        "repetition": int(identity["repetition"]),
        "budget": budget,
        "run_dir": str(run_dir),
        "real_attempts": len(attempts(run_dir)),
        "numeric_scores": sum(x.get("score") is not None for x in attempts(run_dir)),
        "migrations": len(list(run_dir.glob(".coral/islands/*/notes/migrations/migration_*.md"))),
        "best_artifact_score": best[2],
        "best_exact_blocks": best[3],
        "best_exact_pairs": best[4],
        "baseline_artifact_score": base_score,
        "best_so_far_auc": statistics.fmean(progress) if progress else base_score,
        "latest_diversity": statistics.fmean(distances) if distances else 0.0,
        "parse_errors": ";".join(parse_errors),
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
                    for metric in ("best_artifact_score", "best_exact_blocks", "best_so_far_auc"):
                        lv = [float(x[metric]) for x in left]
                        rv = [float(x[metric]) for x in right]
                        low, high = bootstrap_difference(lv, rv, f"{budget}:{task}:{reference}:{metric}")
                        contrasts.append({"budget": budget, "task": task, "contrast": f"multi_island_minus_{reference}", "metric": metric, "difference": statistics.fmean(lv) - statistics.fmean(rv), "ci_low": low, "ci_high": high})
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "runs.csv", rows)
    write_csv(output / "contrasts.csv", contrasts)
    audit = {"schema_version": 1, "tasks": TASKS, "conditions": CONDITIONS, "budgets": args.budgets, "repetitions": REPETITIONS, "complete_rows": len(rows), "expected_rows": len(TASKS) * len(CONDITIONS) * REPETITIONS * len(args.budgets), "integrity_failures": failures}
    (output / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(f"Audited {len(rows)} complete cells; failures={len(failures)}")
    if failures and not args.allow_incomplete:
        raise SystemExit(f"Active modular matrix incomplete; see {output / 'audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
