#!/usr/bin/env python3
"""Audit modular multi-island runs and compute predeclared contrasts."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from experiments.multi_island_modular import calibrate

ROOT = Path(__file__).resolve().parent
TASKDATA = ROOT / "tasks/modular_landscape/taskdata"
TASKS = (
    "smooth_modular128",
    "rugged_modular128",
    "smooth_modular192",
    "rugged_modular192",
)
CONDITIONS = ("global", "partition", "multi_island")
REPETITIONS = 8


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=Path("/var/tmp/coral-institutions-results/modular-v1"))
    parser.add_argument("--budgets", type=int, nargs="+", default=[64, 128, 256, 512])
    parser.add_argument("--output-dir", type=Path, default=ROOT / "analysis")
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def task_config(task: str) -> dict[str, Any]:
    return load_json(TASKDATA / f"{task}.json") or {}


def parse_candidate(source: str, n: int) -> str:
    tree = ast.parse(source)
    values: list[str] = []
    for node in tree.body:
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "CANDIDATE" for target in node.targets
        ):
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "CANDIDATE":
            value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            values.append(value.value)
    if len(values) != 1 or len(values[0]) != n or set(values[0]) - {"0", "1"}:
        raise ValueError("invalid literal candidate")
    return values[0]


def source_at(run_dir: Path, commit: str, task: str) -> str:
    import subprocess

    filename = "candidate192.py" if task.endswith("192") else "candidate.py"
    result = subprocess.run(
        ["git", "-C", str(run_dir / "repo"), "show", f"{commit}:{filename}"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise ValueError(f"cannot read candidate at {commit}: {result.stderr.strip()}")
    return result.stdout


def candidate_metrics(candidate: str, task: str) -> tuple[float, int, int]:
    config = task_config(task)
    blocks = int(config["blocks"])
    width = int(config["block_width"])
    return calibrate.score(
        candidate,
        mode=str(config["mode"]),
        seed=str(config["seed"]),
        blocks=blocks,
        width=width,
    )


def real_attempts(run_dir: Path) -> list[dict[str, Any]]:
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
    return sorted(records.values(), key=lambda item: (str(item.get("timestamp", "")), str(item.get("commit_hash", ""))))


def migration_count(run_dir: Path) -> int:
    return len(list(run_dir.glob(".coral/islands/*/notes/migrations/migration_*.md")))


def command_overrides(identity: dict[str, Any]) -> dict[str, str]:
    command = identity.get("command", [])
    return {
        item.split("=", 1)[0]: item.split("=", 1)[1]
        for item in command
        if isinstance(item, str) and "=" in item
    }


def integrity_reasons(run_dir: Path, identity: dict[str, Any], budget: int) -> list[str]:
    reasons: list[str] = []
    overrides = command_overrides(identity)
    condition = str(identity.get("condition"))
    expected_islands = {"global": ("1", "false"), "partition": ("2", "false"), "multi_island": ("2", "true")}.get(condition)
    if expected_islands is None:
        reasons.append(f"unknown condition {condition!r}")
    else:
        if overrides.get("islands.count") != expected_islands[0]:
            reasons.append("wrong islands.count")
        if overrides.get("islands.migration.enabled") != expected_islands[1]:
            reasons.append("wrong migration setting")
    expected_every = max(8, budget // 4)
    for key, expected in {
        "agents.count": "4",
        "agents.runtime": "opencode",
        "agents.model": "mafia/glm-5.2",
        "grader.args.disable_tune": "true",
        "run.stop.max_real_attempts": str(budget),
        "islands.migration.every": str(expected_every),
        "islands.migration.rank_window": str(expected_every),
        "islands.migration.remigration_cooldown": "8",
    }.items():
        if overrides.get(key) != expected:
            reasons.append(f"{key}={overrides.get(key)!r}, expected {expected!r}")
    role = next((value for key, value in overrides.items() if key == "agents.runtime_options.role_file"), "")
    if role != str(ROOT / "eval_protocol.md"):
        reasons.append("wrong modular role protocol")
    private = run_dir / ".coral/private" / f"{identity.get('task')}.json"
    frozen = TASKDATA / f"{identity.get('task')}.json"
    if not private.is_file() or not frozen.is_file() or private.read_bytes() != frozen.read_bytes():
        reasons.append("private taskdata does not match frozen taskdata")
    attempts = real_attempts(run_dir)
    if len(attempts) != budget:
        reasons.append(f"real attempts={len(attempts)}, expected {budget}")
    auto_stop = load_json(run_dir / ".coral/public/auto_stop.json") or {}
    if auto_stop.get("reason") != "max_real_attempts":
        reasons.append(f"auto-stop reason={auto_stop.get('reason')!r}")
    if condition != "multi_island" and migration_count(run_dir):
        reasons.append("migration notes in no-migration control")
    return reasons


def collect_run(run_dir: Path, identity: dict[str, Any], budget: int) -> dict[str, Any]:
    task = str(identity["task"])
    config = task_config(task)
    n = int(config["blocks"]) * int(config["block_width"])
    attempts = real_attempts(run_dir)
    parsed: list[tuple[dict[str, Any], str, float, int, int]] = []
    errors: list[str] = []
    for record in attempts:
        try:
            candidate = parse_candidate(source_at(run_dir, str(record["commit_hash"]), task), n)
            score, exact, pairs = candidate_metrics(candidate, task)
            parsed.append((record, candidate, score, exact, pairs))
        except (OSError, ValueError, KeyError, TypeError, SyntaxError):
            errors.append(str(record.get("commit_hash")))
    baseline = "0" * n
    baseline_score, baseline_exact, baseline_pairs = candidate_metrics(baseline, task)
    if parsed:
        best_score = max(float(item[0]["score"]) for item in parsed if item[0].get("score") is not None)
        best_item = max(parsed, key=lambda item: item[2])
        progress: list[float] = []
        current = baseline_score
        for record, _candidate, recomputed, _exact, _pairs in parsed:
            if isinstance(record.get("score"), (int, float)):
                current = max(current, float(record["score"]))
            progress.append(current)
        auc = statistics.fmean(progress)
    else:
        best_score = baseline_score
        best_item = ({}, baseline, baseline_score, baseline_exact, baseline_pairs)
        auc = baseline_score
    # A per-agent latest candidate distance is a useful secondary diagnostic.
    latest: dict[str, str] = {}
    for record, candidate, _score, _exact, _pairs in parsed:
        agent = str(record.get("agent_id") or "unknown")
        latest[agent] = candidate
    candidates = list(latest.values())
    distances = [
        sum(a != b for a, b in zip(left, right, strict=True)) / n
        for index, left in enumerate(candidates)
        for right in candidates[index + 1 :]
    ]
    return {
        "task": task,
        "condition": str(identity["condition"]),
        "repetition": int(identity["repetition"]),
        "budget": budget,
        "run_dir": str(run_dir),
        "real_attempts": len(attempts),
        "numeric_scores": sum(record.get("score") is not None for record in attempts),
        "grader_errors": sum(record.get("metadata", {}).get("budget_class") == "grader_error" for record in attempts),
        "migrations": migration_count(run_dir),
        "best_score": best_score,
        "best_exact_blocks": best_item[3],
        "best_exact_pairs": best_item[4],
        "baseline_score": baseline_score,
        "auc_score": auc,
        "latest_diversity": statistics.fmean(distances) if distances else 0.0,
        "parse_errors": ";".join(errors),
    }


def bootstrap_ci(values: list[float], seed_text: str) -> tuple[float, float]:
    if not values:
        return float("nan"), float("nan")
    if len(values) == 1:
        return values[0], values[0]
    seed = int.from_bytes(hashlib.sha256(seed_text.encode()).digest()[:8], "big")
    rng = random.Random(seed)
    means = [statistics.fmean(rng.choices(values, k=len(values))) for _ in range(4000)]
    means.sort()
    return means[int(0.025 * len(means))], means[int(0.975 * len(means))]


def bootstrap_difference(left: list[float], right: list[float], seed_text: str) -> tuple[float, float]:
    if not left or not right:
        return float("nan"), float("nan")
    if len(left) == len(right) == 1:
        return left[0] - right[0], left[0] - right[0]
    seed = int.from_bytes(hashlib.sha256(seed_text.encode()).digest()[:8], "big")
    rng = random.Random(seed)
    differences = [
        statistics.fmean(rng.choices(left, k=len(left)))
        - statistics.fmean(rng.choices(right, k=len(right)))
        for _ in range(4000)
    ]
    differences.sort()
    return differences[int(0.025 * len(differences))], differences[int(0.975 * len(differences))]


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
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    root = args.results_root.resolve()
    for budget in args.budgets:
        slice_root = root / f"budget-{budget}"
        for task in TASKS:
            for condition in CONDITIONS:
                for repetition in range(1, REPETITIONS + 1):
                    matches = list(slice_root.glob(f"{task}/{condition}/rep-{repetition:02d}/operator-command.json"))
                    if not matches:
                        failures.append({"budget": budget, "task": task, "condition": condition, "repetition": repetition, "run_dir": "", "reasons": ["missing run"]})
                        continue
                    command_path = matches[-1]
                    identity = load_json(command_path)
                    if identity is None:
                        failures.append({"budget": budget, "task": task, "condition": condition, "repetition": repetition, "run_dir": str(command_path.parent), "reasons": ["unreadable operator command"]})
                        continue
                    run_dir = command_path.parent
                    reasons = integrity_reasons(run_dir, identity, budget)
                    if reasons:
                        failures.append({"budget": budget, "task": task, "condition": condition, "repetition": repetition, "run_dir": str(run_dir), "reasons": reasons})
                    else:
                        rows.append(collect_run(run_dir, identity, budget))
    contrasts: list[dict[str, Any]] = []
    grouped: dict[tuple[int, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(int(row["budget"]), str(row["task"]), str(row["condition"]))].append(row)
    if not failures:
        for budget in args.budgets:
            for task in TASKS:
                for reference in ("global", "partition"):
                    left = grouped[(budget, task, "multi_island")]
                    right = grouped[(budget, task, reference)]
                    for metric in ("best_score", "best_exact_blocks", "auc_score"):
                        difference = statistics.fmean(float(item[metric]) for item in left) - statistics.fmean(float(item[metric]) for item in right)
                        low, high = bootstrap_difference(
                            [float(item[metric]) for item in left],
                            [float(item[metric]) for item in right],
                            f"{budget}:{task}:{reference}:{metric}",
                        )
                        contrasts.append({
                            "budget": budget,
                            "task": task,
                            "contrast": f"multi_island_minus_{reference}",
                            "metric": metric,
                            "difference": difference,
                            "bootstrap_low": low,
                            "bootstrap_high": high,
                        })
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "runs.csv", rows)
    write_csv(output / "contrasts.csv", contrasts)
    audit = {
        "schema_version": 1,
        "tasks": TASKS,
        "conditions": CONDITIONS,
        "budgets": args.budgets,
        "repetitions": REPETITIONS,
        "complete_rows": len(rows),
        "expected_rows": len(TASKS) * len(CONDITIONS) * REPETITIONS * len(args.budgets),
        "integrity_failures": failures,
        "interpretation": "Only complete eight-seed cells are eligible for topology contrasts.",
    }
    (output / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(f"Audited {len(rows)} complete cells; failures={len(failures)}")
    if failures and not args.allow_incomplete:
        raise SystemExit(f"Modular matrix incomplete or invalid; see {output / 'audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
