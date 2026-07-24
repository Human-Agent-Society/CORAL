#!/usr/bin/env python3
"""Audit the experiment matrix and generate tables plus self-contained SVGs."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import math
import random
import statistics
import subprocess
import tokenize
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_ROOT = Path("/var/tmp/coral-institutions-results/matrix")
EXPECTED_ATTEMPTS = 16
REPETITIONS = 3
TASK_CONDITIONS = {
    "kernel": ("global", "partition", "multi_island", "independent"),
    "smooth": ("global", "partition", "multi_island"),
    "rugged": ("global", "partition", "multi_island"),
}
TASK_LABELS = {
    "kernel": "Kernel Builder",
    "smooth": "Smooth NK (K=0)",
    "rugged": "Rugged NK (K=4)",
}
CONDITION_LABELS = {
    "global": "Global",
    "partition": "Partition",
    "multi_island": "Multi-island",
    "independent": "Independent",
}
COLORS = {
    "global": "#667085",
    "partition": "#D97706",
    "multi_island": "#0F766E",
    "independent": "#7C3AED",
}
TUNE_DISABLED_MARKER = "Tune mode is disabled for this controlled experiment"


@dataclass
class Attempt:
    commit_hash: str
    agent_id: str
    score: float | None
    timestamp: str
    source: str
    candidate: str | None


@dataclass
class Run:
    task: str
    condition: str
    repetition: int
    path: Path
    attempts: list[Attempt]
    agent_ids: list[str]
    baseline_source: str
    total_real: int
    grader_errors: int
    tune_attempts: int
    tune_protocol_violations: int
    migrations: int
    migration_eval_counts: list[int]
    configuration_errors: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "experiments/multi_island/analysis",
    )
    parser.add_argument("--blog-dir", type=Path, default=REPO_ROOT / "blog")
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--no-blog", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def attempt_records(run_dir: Path) -> tuple[list[dict[str, Any]], int, int, int]:
    records: dict[str, dict[str, Any]] = {}
    grader_errors: set[str] = set()
    tune_attempts: set[str] = set()
    tune_protocol_violations: set[str] = set()
    for path in run_dir.glob(".coral/**/attempts/*.json"):
        record = load_json(path)
        if record is None:
            continue
        commit_hash = record.get("commit_hash")
        if not isinstance(commit_hash, str):
            continue
        if record.get("status") == "pending":
            continue
        budget_class = record.get("metadata", {}).get("budget_class", "real")
        if budget_class == "grader_error":
            grader_errors.add(commit_hash)
        elif budget_class == "tune":
            tune_attempts.add(commit_hash)
            if record.get("score") is not None or TUNE_DISABLED_MARKER not in str(
                record.get("feedback") or ""
            ):
                tune_protocol_violations.add(commit_hash)
        elif budget_class == "real":
            records[commit_hash] = record
    ordered = sorted(
        records.values(),
        key=lambda item: (item.get("timestamp") or "", item.get("commit_hash") or ""),
    )
    return (
        ordered,
        len(grader_errors),
        len(tune_attempts),
        len(tune_protocol_violations),
    )


def configuration_errors(run_dir: Path, identity: dict[str, Any]) -> list[str]:
    command = identity.get("command")
    if not isinstance(command, list):
        return ["operator command missing"]
    overrides = {
        item.split("=", 1)[0]: item.split("=", 1)[1]
        for item in command
        if isinstance(item, str) and "=" in item
    }
    condition = str(identity["condition"])
    topology = {
        "global": ("1", "false"),
        "partition": ("2", "false"),
        "multi_island": ("2", "true"),
        "independent": ("4", "false"),
    }[condition]
    expected = {
        "agents.count": "4",
        "agents.runtime": "opencode",
        "agents.model": "mafia/glm-5.2",
        "agents.research": "false",
        "agents.sandbox.enabled": "true",
        "agents.sandbox.provider": "srt",
        "agents.sandbox.network": "open",
        "grader.parallel.max_workers": "1",
        "grader.args.disable_tune": "true",
        "islands.count": topology[0],
        "islands.migration.enabled": topology[1],
        "islands.migration.every": "6",
        "islands.migration.rank_window": "6",
        "islands.migration.min_evals": "1",
        "islands.migration.max_per_cycle": "2",
        "islands.migration.remigration_cooldown": "6",
        "run.session": "local",
        "run.stop.max_real_attempts": str(EXPECTED_ATTEMPTS),
        "workspace.run_dir": str(run_dir),
    }
    errors = [
        f"{key}={overrides.get(key)!r}, expected {value!r}"
        for key, value in expected.items()
        if overrides.get(key) != value
    ]
    if str(identity["task"]) == "kernel":
        if overrides.get("grader.args.harden_candidate") != "true":
            errors.append(
                "grader.args.harden_candidate="
                f"{overrides.get('grader.args.harden_candidate')!r}, expected 'true'"
            )

    config_path = run_dir / ".coral/config.yaml"
    if not config_path.is_file():
        errors.append("resolved .coral/config.yaml missing")
    else:
        try:
            resolved = yaml.safe_load(config_path.read_text())
        except (OSError, yaml.YAMLError) as exc:
            errors.append(f"resolved .coral/config.yaml unreadable: {exc}")
            resolved = None
        if isinstance(resolved, dict):
            expected_resolved = {
                "agents.count": 4,
                "agents.runtime": "opencode",
                "agents.model": "mafia/glm-5.2",
                "agents.research": False,
                "agents.sandbox.enabled": True,
                "agents.sandbox.provider": "srt",
                "agents.sandbox.network": "open",
                "grader.parallel.max_workers": 1,
                "grader.args.disable_tune": True,
                "islands.count": int(topology[0]),
                "islands.migration.enabled": topology[1] == "true",
                "islands.migration.every": 6,
                "islands.migration.rank_window": 6,
                "islands.migration.min_evals": 1,
                "islands.migration.max_per_cycle": 2,
                "islands.migration.remigration_cooldown": 6,
                "run.session": "local",
                "run.stop.max_real_attempts": EXPECTED_ATTEMPTS,
                "workspace.run_dir": str(run_dir),
            }
            for key, expected_value in expected_resolved.items():
                value: Any = resolved
                for part in key.split("."):
                    value = value.get(part) if isinstance(value, dict) else None
                if value != expected_value:
                    errors.append(f"resolved {key}={value!r}, expected {expected_value!r}")

            if str(identity["task"]) == "kernel":
                grader = resolved.get("grader", {})
                args = grader.get("args", {}) if isinstance(grader, dict) else {}
                if args.get("harden_candidate") is not True:
                    errors.append(
                        "resolved grader.args.harden_candidate is not true"
                    )
                timeout_pair = (
                    grader.get("timeout") if isinstance(grader, dict) else None,
                    args.get("evaluation_timeout") if isinstance(args, dict) else None,
                )
                if timeout_pair not in {(120, None), (150, 120)}:
                    errors.append(
                        "resolved kernel timeout pair="
                        f"{timeout_pair!r}, expected legacy (120, None) or guarded (150, 120)"
                    )
        elif resolved is not None:
            errors.append("resolved .coral/config.yaml is not a mapping")
    sandbox_dir = run_dir / ".coral/private/sandbox"
    if len(list(sandbox_dir.glob("*.json"))) != 4:
        errors.append("expected four SRT sandbox configs")

    task = str(identity["task"])
    if task in {"smooth", "rugged"}:
        frozen = (
            REPO_ROOT
            / "experiments/multi_island/tasks/institutional_landscape/taskdata"
            / f"{task}.json"
        )
        copied = run_dir / ".coral/private" / f"{task}.json"
        if not copied.is_file() or copied.read_bytes() != frozen.read_bytes():
            errors.append(f"private {task}.json does not match frozen landscape")
    return errors


def git_source(run_dir: Path, commit_hash: str, filename: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(run_dir / "repo"), "show", f"{commit_hash}:{filename}"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Cannot read {filename} at {commit_hash} in {run_dir}: {result.stderr.strip()}"
        )
    return result.stdout


def candidate_from_source(source: str) -> str:
    tree = ast.parse(source)
    values: list[str] = []
    for node in tree.body:
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == "CANDIDATE" for target in node.targets
            ):
                value = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "CANDIDATE":
                value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            values.append(value.value)
    if len(values) != 1:
        raise ValueError("evaluated candidate source does not contain one literal CANDIDATE")
    return values[0]


def load_run(run_dir: Path, identity: dict[str, Any]) -> Run:
    task = str(identity["task"])
    filename = "kernel_builder.py" if task == "kernel" else "candidate.py"
    records, grader_errors, tune_attempts, tune_protocol_violations = attempt_records(run_dir)
    attempts: list[Attempt] = []
    for record in records:
        score = record.get("score")
        numeric_score = (
            float(score) if isinstance(score, (int, float)) and math.isfinite(score) else None
        )
        source = git_source(run_dir, record["commit_hash"], filename)
        candidate: str | None = None
        if task != "kernel":
            try:
                candidate = candidate_from_source(source)
            except (SyntaxError, ValueError):
                if numeric_score is not None:
                    raise  # A scored controlled candidate must satisfy the literal contract.
        attempts.append(
            Attempt(
                commit_hash=record["commit_hash"],
                agent_id=str(record.get("agent_id") or "unknown"),
                score=numeric_score,
                timestamp=str(record.get("timestamp") or ""),
                source=source,
                candidate=candidate,
            )
        )
    migration_notes = sorted(
        run_dir.glob(".coral/islands/*/notes/migrations/migration_*.md"),
        key=lambda path: (path.stat().st_mtime, str(path)),
    )
    attempt_times = [
        datetime.fromisoformat(attempt.timestamp).timestamp()
        for attempt in attempts
        if attempt.timestamp
    ]
    migration_eval_counts = [
        sum(timestamp <= note.stat().st_mtime for timestamp in attempt_times)
        for note in migration_notes
    ]
    agent_ids = sorted(path.name for path in (run_dir / "agents").iterdir() if path.is_dir())
    return Run(
        task=task,
        condition=str(identity["condition"]),
        repetition=int(identity["repetition"]),
        path=run_dir,
        attempts=attempts[:EXPECTED_ATTEMPTS],
        agent_ids=agent_ids,
        baseline_source=(run_dir / "repo" / filename).read_text(),
        total_real=len(records),
        grader_errors=grader_errors,
        tune_attempts=tune_attempts,
        tune_protocol_violations=tune_protocol_violations,
        migrations=len(migration_notes),
        migration_eval_counts=migration_eval_counts,
        configuration_errors=configuration_errors(run_dir, identity),
    )


def run_audit_row(
    run: Run,
    *,
    auto_stop_reason: str | None,
    invalid_reason: str = "",
) -> dict[str, Any]:
    return {
        "task": run.task,
        "condition": run.condition,
        "repetition": run.repetition,
        "run_dir": str(run.path),
        "finalized_real_attempts": len(run.attempts),
        "total_real_records": run.total_real,
        "grader_errors": run.grader_errors,
        "tune_attempts": run.tune_attempts,
        "tune_protocol_violations": run.tune_protocol_violations,
        "migrations": run.migrations,
        "migration_eval_counts": run.migration_eval_counts,
        "auto_stop_reason": auto_stop_reason,
        "invalid_reason": invalid_reason,
    }


def discover_runs(results_root: Path) -> tuple[list[Run], list[dict[str, Any]]]:
    candidates: dict[tuple[str, str, int], list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    incomplete: list[dict[str, Any]] = []
    for command_path in results_root.rglob("operator-command.json"):
        identity = load_json(command_path)
        if identity is None:
            continue
        run_dir = command_path.parent
        key = (str(identity["task"]), str(identity["condition"]), int(identity["repetition"]))
        candidates[key].append((run_dir, identity))

    runs: list[Run] = []
    for task, conditions in TASK_CONDITIONS.items():
        for condition in conditions:
            for repetition in range(1, REPETITIONS + 1):
                key = (task, condition, repetition)
                complete_options: list[Run] = []
                for run_dir, identity in candidates.get(key, []):
                    invalid = load_json(run_dir / "experiment-invalid.json")
                    if invalid is not None:
                        (
                            invalid_records,
                            invalid_grader_errors,
                            invalid_tune_attempts,
                            invalid_tune_protocol_violations,
                        ) = attempt_records(run_dir)
                        incomplete.append(
                            {
                                "task": task,
                                "condition": condition,
                                "repetition": repetition,
                                "run_dir": str(run_dir),
                                "finalized_real_attempts": len(invalid_records),
                                "total_real_records": len(invalid_records),
                                "grader_errors": invalid_grader_errors,
                                "tune_attempts": invalid_tune_attempts,
                                "tune_protocol_violations": invalid_tune_protocol_violations,
                                "migrations": len(
                                    list(
                                        run_dir.glob(
                                            ".coral/islands/*/notes/migrations/migration_*.md"
                                        )
                                    )
                                ),
                                "migration_eval_counts": [],
                                "auto_stop_reason": "experiment_invalid",
                                "invalid_reason": invalid.get("reason", "unspecified"),
                            }
                        )
                        continue
                    run = load_run(run_dir, identity)
                    auto_stop = load_json(run_dir / ".coral/public/auto_stop.json") or {}
                    completed_budget = (
                        len(run.attempts) >= EXPECTED_ATTEMPTS
                        and auto_stop.get("reason") == "max_real_attempts"
                    )
                    protocol_errors = list(run.configuration_errors)
                    if run.grader_errors:
                        protocol_errors.append(
                            f"{run.grader_errors} grader infrastructure error(s)"
                        )
                    if run.tune_protocol_violations:
                        protocol_errors.append(
                            f"{run.tune_protocol_violations} tune protocol violation(s)"
                        )
                    if completed_budget and not protocol_errors:
                        complete_options.append(run)
                    else:
                        incomplete.append(
                            run_audit_row(
                                run,
                                auto_stop_reason=(
                                    "protocol_invalid"
                                    if completed_budget and protocol_errors
                                    else auto_stop.get("reason")
                                ),
                                invalid_reason="; ".join(protocol_errors),
                            )
                        )
                if complete_options:
                    ordered = sorted(complete_options, key=lambda run: str(run.path))
                    runs.append(ordered[-1])
                    incomplete.extend(
                        run_audit_row(
                            superseded,
                            auto_stop_reason="superseded_complete",
                            invalid_reason=f"Superseded by {ordered[-1].path}",
                        )
                        for superseded in ordered[:-1]
                    )
                else:
                    incomplete.append(
                        {
                            "task": task,
                            "condition": condition,
                            "repetition": repetition,
                            "run_dir": "",
                            "finalized_real_attempts": 0,
                            "total_real_records": 0,
                            "grader_errors": 0,
                            "tune_attempts": 0,
                            "tune_protocol_violations": 0,
                            "migrations": 0,
                            "migration_eval_counts": [],
                            "auto_stop_reason": "missing",
                            "invalid_reason": "",
                        }
                    )
    return runs, incomplete


def landscape_fitness(candidate: str, config_name: str) -> float:
    path = (
        REPO_ROOT
        / "experiments/multi_island/tasks/institutional_landscape/taskdata"
        / f"{config_name}.json"
    )
    config = json.loads(path.read_text())
    k = int(config["k"])
    seed = str(config["seed"])
    values = []
    for index in range(len(candidate)):
        pattern = "".join(candidate[(index + offset) % len(candidate)] for offset in range(k + 1))
        digest = hashlib.sha256(f"{seed}:{index}:{pattern}".encode()).digest()
        values.append(int.from_bytes(digest[:8], "big") / 2**64)
    return sum(values) / len(values)


BASELINES = {
    "kernel": 11_910.0,
    "smooth": landscape_fitness("0" * 20, "smooth"),
    "rugged": landscape_fitness("0" * 20, "rugged"),
}


def best_score(run: Run) -> float:
    scores = [
        BASELINES[run.task],
        *(attempt.score for attempt in run.attempts if attempt.score is not None),
    ]
    return min(scores) if run.task == "kernel" else max(scores)


def gain(run: Run, score: float | None = None) -> float:
    score = best_score(run) if score is None else score
    baseline = BASELINES[run.task]
    if run.task == "kernel":
        return 100 * (baseline - score) / baseline
    return 100 * (score - baseline)


def best_so_far(run: Run) -> list[float]:
    values: list[float] = []
    current = BASELINES[run.task]
    for attempt in run.attempts:
        if attempt.score is not None:
            current = (
                min(current, attempt.score) if run.task == "kernel" else max(current, attempt.score)
            )
        values.append(current)
    return values


def token_shingles(source: str, width: int = 5) -> set[tuple[str, ...]]:
    ignored = {
        tokenize.ENCODING,
        tokenize.ENDMARKER,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.NEWLINE,
        tokenize.NL,
        tokenize.COMMENT,
    }
    try:
        tokens = [
            token.string
            for token in tokenize.generate_tokens(io.StringIO(source).readline)
            if token.type not in ignored
        ]
    except (IndentationError, tokenize.TokenError):
        tokens = source.split()
    return {
        tuple(tokens[index : index + width]) for index in range(max(0, len(tokens) - width + 1))
    }


def source_distance(task: str, left: str, right: str) -> float:
    if task != "kernel":
        a = candidate_from_source(left)
        b = candidate_from_source(right)
        return sum(x != y for x, y in zip(a, b, strict=True)) / len(a)
    a = token_shingles(left)
    b = token_shingles(right)
    union = a | b
    return 0.0 if not union else 1 - len(a & b) / len(union)


def diversity_at(run: Run, count: int) -> float:
    latest: dict[str, Attempt] = {}
    for attempt in run.attempts[:count]:
        if run.task != "kernel" and attempt.candidate is None:
            continue
        latest[attempt.agent_id] = attempt
    baseline_candidate = (
        None if run.task == "kernel" else candidate_from_source(run.baseline_source)
    )
    solutions = [
        latest.get(
            agent_id,
            Attempt(
                commit_hash="seed",
                agent_id=agent_id,
                score=BASELINES[run.task],
                timestamp="",
                source=run.baseline_source,
                candidate=baseline_candidate,
            ),
        )
        for agent_id in run.agent_ids
    ]
    distances = [
        source_distance(run.task, solutions[i].source, solutions[j].source)
        for i in range(len(solutions))
        for j in range(i + 1, len(solutions))
    ]
    return statistics.fmean(distances) if distances else 0.0


def run_row(run: Run) -> dict[str, Any]:
    progress = best_so_far(run)
    return {
        "task": run.task,
        "condition": run.condition,
        "repetition": run.repetition,
        "run_dir": str(run.path),
        "real_attempts_used": len(run.attempts),
        "numeric_scores": sum(attempt.score is not None for attempt in run.attempts),
        "total_real_records": run.total_real,
        "overshoot": max(0, run.total_real - EXPECTED_ATTEMPTS),
        "grader_errors": run.grader_errors,
        "tune_attempts": run.tune_attempts,
        "tune_protocol_violations": run.tune_protocol_violations,
        "migrations": run.migrations,
        "migration_eval_counts": "|".join(map(str, run.migration_eval_counts)),
        "configuration_errors": "; ".join(run.configuration_errors),
        "baseline_score": BASELINES[run.task],
        "best_score": best_score(run),
        "gain": gain(run),
        "best_so_far_auc": statistics.fmean(gain(run, score) for score in progress),
        "diversity_eval_8": diversity_at(run, 8),
        "diversity_eval_16": diversity_at(run, 16),
    }


def percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - index) + ordered[upper] * (index - lower)


def bootstrap_ci(values: Sequence[float], *, seed: int) -> tuple[float, float]:
    if len(values) == 1:
        return values[0], values[0]
    rng = random.Random(seed)
    means = [statistics.fmean(rng.choice(values) for _ in values) for _ in range(10_000)]
    return percentile(means, 0.025), percentile(means, 0.975)


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["task"], row["condition"])].append(row)
    output: list[dict[str, Any]] = []
    metrics = ("best_score", "gain", "best_so_far_auc", "diversity_eval_8", "diversity_eval_16")
    for (task, condition), group in sorted(grouped.items()):
        summary: dict[str, Any] = {"task": task, "condition": condition, "n": len(group)}
        for metric in metrics:
            values = [float(row[metric]) for row in group]
            digest = hashlib.sha256(f"{task}:{condition}:{metric}".encode()).digest()
            low, high = bootstrap_ci(values, seed=int.from_bytes(digest[:8], "big"))
            summary[f"{metric}_mean"] = statistics.fmean(values)
            summary[f"{metric}_sd"] = statistics.stdev(values) if len(values) > 1 else 0.0
            summary[f"{metric}_ci_low"] = low
            summary[f"{metric}_ci_high"] = high
        summary["migrations_total"] = sum(int(row["migrations"]) for row in group)
        summary["grader_errors_total"] = sum(int(row["grader_errors"]) for row in group)
        summary["tune_attempts_total"] = sum(int(row["tune_attempts"]) for row in group)
        summary["tune_protocol_violations_total"] = sum(
            int(row["tune_protocol_violations"]) for row in group
        )
        summary["overshoot_total"] = sum(int(row["overshoot"]) for row in group)
        output.append(summary)
    return output


def bootstrap_difference(
    left: Sequence[float], right: Sequence[float], *, seed: int
) -> tuple[float, float]:
    rng = random.Random(seed)
    differences = [
        statistics.fmean(rng.choice(left) for _ in left)
        - statistics.fmean(rng.choice(right) for _ in right)
        for _ in range(10_000)
    ]
    return percentile(differences, 0.025), percentile(differences, 0.975)


def contrast_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["task"], row["condition"])].append(row)

    comparisons = [
        (task, "multi_island", reference)
        for task in TASK_CONDITIONS
        for reference in (
            ("global", "partition", "independent") if task == "kernel" else ("global", "partition")
        )
    ]
    metrics = ("gain", "best_so_far_auc", "diversity_eval_16")
    output: list[dict[str, Any]] = []
    for task, left_condition, right_condition in comparisons:
        result: dict[str, Any] = {
            "task": task,
            "contrast": f"{left_condition}_minus_{right_condition}",
        }
        for metric in metrics:
            left = [float(row[metric]) for row in grouped[(task, left_condition)]]
            right = [float(row[metric]) for row in grouped[(task, right_condition)]]
            digest = hashlib.sha256(
                f"{task}:{left_condition}:{right_condition}:{metric}".encode()
            ).digest()
            low, high = bootstrap_difference(
                left,
                right,
                seed=int.from_bytes(digest[:8], "big"),
            )
            result[f"{metric}_difference"] = statistics.fmean(left) - statistics.fmean(right)
            result[f"{metric}_ci_low"] = low
            result[f"{metric}_ci_high"] = high
        output.append(result)

    interaction: dict[str, Any] = {
        "task": "controlled_interaction",
        "contrast": "rugged_minus_smooth_of_multi_island_minus_global",
    }
    for metric in metrics:
        cells = {
            (task, condition): [float(row[metric]) for row in grouped[(task, condition)]]
            for task in ("smooth", "rugged")
            for condition in ("global", "multi_island")
        }
        point = (
            statistics.fmean(cells[("rugged", "multi_island")])
            - statistics.fmean(cells[("rugged", "global")])
            - statistics.fmean(cells[("smooth", "multi_island")])
            + statistics.fmean(cells[("smooth", "global")])
        )
        digest = hashlib.sha256(f"controlled-interaction:{metric}".encode()).digest()
        rng = random.Random(int.from_bytes(digest[:8], "big"))
        samples = []
        for _ in range(10_000):
            means = {
                key: statistics.fmean(rng.choice(values) for _ in values)
                for key, values in cells.items()
            }
            samples.append(
                means[("rugged", "multi_island")]
                - means[("rugged", "global")]
                - means[("smooth", "multi_island")]
                + means[("smooth", "global")]
            )
        interaction[f"{metric}_difference"] = point
        interaction[f"{metric}_ci_low"] = percentile(samples, 0.025)
        interaction[f"{metric}_ci_high"] = percentile(samples, 0.975)
    output.append(interaction)
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def svg_document(width: int, height: int, body: Iterable[str], title: str) -> str:
    return (
        "\n".join(
            [
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
                f'<title id="title">{escape(title)}</title>',
                '<desc id="desc">Run-level points, means, and replicate-bootstrap intervals.</desc>',
                "<style>text{font-family:Inter,ui-sans-serif,system-ui,sans-serif;fill:#1D2939}.axis{stroke:#98A2B3;stroke-width:1}.grid{stroke:#EAECF0;stroke-width:1}.mean{stroke:#101828;stroke-width:1.5}.ci{stroke:#344054;stroke-width:2}.point{stroke:white;stroke-width:1.2}</style>",
                *body,
                "</svg>",
            ]
        )
        + "\n"
    )


def panel_chart(
    rows: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    *,
    metric: str,
    title: str,
    y_label: str,
    scale: float = 1.0,
) -> str:
    width, height = 1120, 410
    margin_left, margin_right, margin_top, margin_bottom = 65, 25, 62, 82
    gap = 34
    panel_width = (width - margin_left - margin_right - 2 * gap) / 3
    plot_height = height - margin_top - margin_bottom
    body = [f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>']
    body.append(
        f'<text x="{width / 2}" y="28" text-anchor="middle" font-size="19" font-weight="700">{escape(title)}</text>'
    )
    body.append(
        f'<text transform="translate(17 {margin_top + plot_height / 2}) rotate(-90)" text-anchor="middle" font-size="12">{escape(y_label)}</text>'
    )

    summary_index = {(row["task"], row["condition"]): row for row in summaries}
    for panel_index, task in enumerate(("kernel", "smooth", "rugged")):
        conditions = TASK_CONDITIONS[task]
        x0 = margin_left + panel_index * (panel_width + gap)
        task_rows = [row for row in rows if row["task"] == task]
        values = [float(row[metric]) * scale for row in task_rows] + [0.0]
        for condition in conditions:
            summary = summary_index[(task, condition)]
            values.extend(
                [
                    float(summary[f"{metric}_ci_low"]) * scale,
                    float(summary[f"{metric}_ci_high"]) * scale,
                ]
            )
        low, high = min(values), max(values)
        padding = max((high - low) * 0.16, 1.0)
        low, high = low - padding, high + padding

        def y(value: float) -> float:
            return margin_top + (high - value) / (high - low) * plot_height

        for tick_index in range(5):
            value = low + (high - low) * tick_index / 4
            yp = y(value)
            body.append(
                f'<line class="grid" x1="{x0:.1f}" y1="{yp:.1f}" x2="{x0 + panel_width:.1f}" y2="{yp:.1f}"/>'
            )
            body.append(
                f'<text x="{x0 - 7:.1f}" y="{yp + 4:.1f}" text-anchor="end" font-size="10">{value:.1f}</text>'
            )
        body.append(
            f'<line class="axis" x1="{x0:.1f}" y1="{margin_top}" x2="{x0:.1f}" y2="{margin_top + plot_height}"/>'
        )
        body.append(
            f'<line class="axis" x1="{x0:.1f}" y1="{y(0):.1f}" x2="{x0 + panel_width:.1f}" y2="{y(0):.1f}"/>'
        )
        body.append(
            f'<text x="{x0 + panel_width / 2:.1f}" y="48" text-anchor="middle" font-size="13" font-weight="650">{escape(TASK_LABELS[task])}</text>'
        )

        slot = panel_width / len(conditions)
        for condition_index, condition in enumerate(conditions):
            center = x0 + slot * (condition_index + 0.5)
            cell_rows = [row for row in task_rows if row["condition"] == condition]
            summary = summary_index[(task, condition)]
            mean = float(summary[f"{metric}_mean"]) * scale
            ci_low = float(summary[f"{metric}_ci_low"]) * scale
            ci_high = float(summary[f"{metric}_ci_high"]) * scale
            body.append(
                f'<line class="ci" x1="{center:.1f}" y1="{y(ci_low):.1f}" x2="{center:.1f}" y2="{y(ci_high):.1f}"/>'
            )
            body.append(
                f'<line class="mean" x1="{center - 13:.1f}" y1="{y(mean):.1f}" x2="{center + 13:.1f}" y2="{y(mean):.1f}"/>'
            )
            offsets = (-7, 0, 7)
            for point_index, row in enumerate(cell_rows):
                value = float(row[metric]) * scale
                body.append(
                    f'<circle class="point" cx="{center + offsets[point_index % 3]:.1f}" cy="{y(value):.1f}" r="4.2" fill="{COLORS[condition]}"/>'
                )
            label = CONDITION_LABELS[condition]
            body.append(
                f'<text transform="translate({center - 2:.1f} {height - margin_bottom + 18}) rotate(-35)" text-anchor="end" font-size="10">{escape(label)}</text>'
            )
    return svg_document(width, height, body, title)


def interaction_chart(rows: list[dict[str, Any]], summaries: list[dict[str, Any]]) -> str:
    width, height = 760, 410
    left, right, top, bottom = 78, 38, 65, 68
    plot_width, plot_height = width - left - right, height - top - bottom
    summary_index = {(row["task"], row["condition"]): row for row in summaries}
    conditions = ("global", "partition", "multi_island")
    values = [
        float(summary_index[(task, condition)]["gain_mean"])
        for task in ("smooth", "rugged")
        for condition in conditions
    ]
    low, high = min([0.0, *values]), max([0.0, *values])
    padding = max((high - low) * 0.18, 1.0)
    low, high = low - padding, high + padding

    def y(value: float) -> float:
        return top + (high - value) / (high - low) * plot_height

    x_positions = {"smooth": left + plot_width * 0.24, "rugged": left + plot_width * 0.76}
    body = [f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>']
    body.append(
        f'<text x="{width / 2}" y="29" text-anchor="middle" font-size="19" font-weight="700">Topology × landscape ruggedness</text>'
    )
    body.append(
        f'<text transform="translate(19 {top + plot_height / 2}) rotate(-90)" text-anchor="middle" font-size="12">Fitness gain from seed (percentage points)</text>'
    )
    for tick_index in range(5):
        value = low + (high - low) * tick_index / 4
        yp = y(value)
        body.append(
            f'<line class="grid" x1="{left}" y1="{yp:.1f}" x2="{width - right}" y2="{yp:.1f}"/>'
        )
        body.append(
            f'<text x="{left - 9}" y="{yp + 4:.1f}" text-anchor="end" font-size="10">{value:.1f}</text>'
        )
    body.append(
        f'<line class="axis" x1="{left}" y1="{y(0):.1f}" x2="{width - right}" y2="{y(0):.1f}"/>'
    )
    for task in ("smooth", "rugged"):
        body.append(
            f'<text x="{x_positions[task]}" y="{height - 39}" text-anchor="middle" font-size="12" font-weight="650">{escape(TASK_LABELS[task])}</text>'
        )
    for condition in conditions:
        points = []
        for task in ("smooth", "rugged"):
            summary = summary_index[(task, condition)]
            points.append((x_positions[task], y(float(summary["gain_mean"]))))
        body.append(
            f'<path d="M {points[0][0]:.1f} {points[0][1]:.1f} L {points[1][0]:.1f} {points[1][1]:.1f}" fill="none" stroke="{COLORS[condition]}" stroke-width="3"/>'
        )
        for x_pos, y_pos in points:
            body.append(
                f'<circle class="point" cx="{x_pos:.1f}" cy="{y_pos:.1f}" r="6" fill="{COLORS[condition]}"/>'
            )
    legend_x = left + 8
    for index, condition in enumerate(conditions):
        x_pos = legend_x + index * 170
        body.append(
            f'<line x1="{x_pos}" y1="48" x2="{x_pos + 22}" y2="48" stroke="{COLORS[condition]}" stroke-width="3"/>'
        )
        body.append(
            f'<text x="{x_pos + 29}" y="52" font-size="11">{escape(CONDITION_LABELS[condition])}</text>'
        )
    return svg_document(width, height, body, "Topology by landscape ruggedness interaction")


def write_attempts_csv(path: Path, runs: list[Run]) -> None:
    rows: list[dict[str, Any]] = []
    for run in runs:
        progress = best_so_far(run)
        for index, (attempt, current_best) in enumerate(
            zip(run.attempts, progress, strict=True), 1
        ):
            rows.append(
                {
                    "task": run.task,
                    "condition": run.condition,
                    "repetition": run.repetition,
                    "evaluation": index,
                    "commit_hash": attempt.commit_hash,
                    "agent_id": attempt.agent_id,
                    "score": attempt.score,
                    "candidate_valid": run.task == "kernel" or attempt.candidate is not None,
                    "best_so_far": current_best,
                    "gain_so_far": gain(run, current_best),
                }
            )
    write_csv(path, rows)


def main() -> int:
    args = parse_args()
    results_root = args.results_root.resolve()
    runs, incomplete = discover_runs(results_root)
    expected = sum(len(conditions) * REPETITIONS for conditions in TASK_CONDITIONS.values())
    missing_cells = [item for item in incomplete if item["auto_stop_reason"] == "missing"]
    if (len(runs) != expected or missing_cells) and not args.allow_incomplete:
        audit_path = args.output_dir / "incomplete-runs.json"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps(incomplete, indent=2) + "\n")
        raise SystemExit(
            f"Matrix incomplete: found {len(runs)}/{expected} complete cells. Audit: {audit_path}"
        )

    rows = [run_row(run) for run in runs]
    summaries = summarize(rows)
    matrix_complete = len(runs) == expected and not missing_cells
    contrasts = contrast_rows(rows) if matrix_complete else []
    integrity_failures = []
    for run in runs:
        reasons = list(run.configuration_errors)
        if run.grader_errors:
            reasons.append(f"{run.grader_errors} grader infrastructure error(s)")
        if run.tune_protocol_violations:
            reasons.append(
                f"{run.tune_protocol_violations} tune attempt(s) bypassed the disabled-tune gate"
            )
        if run.condition != "multi_island" and run.migrations:
            reasons.append("migration note recorded in a no-migration condition")
        if reasons:
            integrity_failures.append(
                {
                    "task": run.task,
                    "condition": run.condition,
                    "repetition": run.repetition,
                    "run_dir": str(run.path),
                    "reasons": reasons,
                }
            )
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "runs.csv", rows)
    write_csv(output_dir / "summary.csv", summaries)
    write_csv(output_dir / "contrasts.csv", contrasts)
    write_attempts_csv(output_dir / "attempts.csv", runs)
    (output_dir / "audit.json").write_text(
        json.dumps(
            {
                "expected_cells": expected,
                "complete_cells": len(runs),
                "expected_attempts_per_cell": EXPECTED_ATTEMPTS,
                "baselines": BASELINES,
                "integrity_failures": integrity_failures,
                "incomplete_or_superseded_runs": incomplete,
            },
            indent=2,
        )
        + "\n"
    )

    if not matrix_complete:
        print(f"Audited {len(runs)}/{expected} complete cells; figures require a full matrix")
        print(f"Run table: {output_dir / 'runs.csv'}")
        return 0
    if integrity_failures:
        raise SystemExit(
            f"Matrix integrity audit failed for {len(integrity_failures)} cell(s); "
            f"see {output_dir / 'audit.json'}"
        )

    performance_svg = panel_chart(
        rows,
        summaries,
        metric="gain",
        title="Multi-island performance across real and controlled tasks",
        y_label="Gain from seed (% fewer cycles / fitness points)",
    )
    diversity_svg = panel_chart(
        rows,
        summaries,
        metric="diversity_eval_16",
        title="Solution diversity after 16 real evaluations",
        y_label="Mean pairwise distance (%)",
        scale=100,
    )
    ruggedness_svg = interaction_chart(rows, summaries)
    (output_dir / "performance.svg").write_text(performance_svg)
    (output_dir / "diversity.svg").write_text(diversity_svg)
    (output_dir / "ruggedness.svg").write_text(ruggedness_svg)

    if not args.no_blog:
        blog_dir = args.blog_dir.resolve()
        blog_dir.mkdir(parents=True, exist_ok=True)
        (blog_dir / "multi-island-performance.svg").write_text(performance_svg)
        (blog_dir / "multi-island-diversity.svg").write_text(diversity_svg)
        (blog_dir / "multi-island-ruggedness.svg").write_text(ruggedness_svg)
        write_csv(blog_dir / "multi-island-results.csv", rows)
        write_csv(blog_dir / "multi-island-summary.csv", summaries)
        write_csv(blog_dir / "multi-island-contrasts.csv", contrasts)

    print(f"Analyzed {len(runs)}/{expected} complete cells")
    print(f"Run table: {output_dir / 'runs.csv'}")
    print(f"Summary:   {output_dir / 'summary.csv'}")
    print(f"Contrasts: {output_dir / 'contrasts.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
