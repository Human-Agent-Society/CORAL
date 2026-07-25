#!/usr/bin/env python3
"""Audit the replicated N=128 boundary/diversity threshold matrix."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from experiments.multi_island import analyze as legacy
from experiments.multi_island_hard.behavior_metrics import behavior_metrics
from experiments.multi_island_hard.run_threshold_v2 import (
    BUDGETS,
    MODEL_API_DOMAINS,
    heartbeat_for,
    migration_every,
)

ROOT = Path(__file__).resolve().parent
TASKDATA = ROOT / "tasks/institutional_landscape/taskdata"
DIAGNOSTICS = ROOT / "threshold_v2_diagnostics.json"
ROLE_FILE = ROOT / "threshold_v2_protocol.md"
TASK_FILES = {
    "smooth128_rep_v2": "smooth128_replicated_v2.json",
    "rugged128_k12_rep_v2": "rugged128_k12_replicated_v2.json",
}
TASKS = tuple(TASK_FILES)
SMOOTH_TASK = "smooth128_rep_v2"
RUGGED_TASK = "rugged128_k12_rep_v2"
PRIMARY_TREATMENT = "multi_island_4"
CONDITIONS = ("global_8", "partition_4", "multi_island_2", PRIMARY_TREATMENT)
PRACTICAL_DELTA_Z = 0.50
MAX_MALFORMED = 1
INITIAL_SALT = "coral-threshold-v2"
AGENT_TIMEOUT = 300
TUNE_DISABLED_MARKER = "Tune mode is disabled for this controlled experiment"
CONTRAST_METRICS = (
    "random_z",
    "reference_gain",
    "best_so_far_auc_reference",
    "midpoint_diversity",
    "final_diversity",
    "duplicate_candidate_rate",
)


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def all_records(run_dir: Path) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for path in run_dir.glob(".coral/**/attempts/*.json"):
        record = load_json(path)
        if record is None or record.get("status") == "pending":
            continue
        commit = record.get("commit_hash")
        if isinstance(commit, str):
            records[commit] = record
    return sorted(
        records.values(),
        key=lambda item: (str(item.get("timestamp", "")), str(item.get("commit_hash", ""))),
    )


def real_records(run_dir: Path) -> list[dict[str, Any]]:
    return [
        record
        for record in all_records(run_dir)
        if record.get("metadata", {}).get("budget_class", "real") == "real"
    ]


def disallowed_records(run_dir: Path) -> list[dict[str, Any]]:
    """Return attempts that obtained free feedback or reflect grader failure.

    A controlled grader may reject ``--tune`` before scoring.  That rejected
    request is useful compliance evidence, but it did not expose a free score
    and must not invalidate an otherwise fixed-real-budget cell.  This mirrors
    the runner's completion rule instead of treating every tune-class record
    as equivalent to a successful tune evaluation.
    """

    violations = []
    for record in all_records(run_dir):
        budget_class = record.get("metadata", {}).get("budget_class", "real")
        if budget_class == "grader_error":
            violations.append(record)
        elif budget_class == "tune" and (
            record.get("score") is not None
            or TUNE_DISABLED_MARKER not in str(record.get("feedback") or "")
        ):
            violations.append(record)
    return violations


def existing_run_dirs(base: Path) -> list[Path]:
    """Return the base cell followed by its numbered retries.

    Failed pilots are deliberately retained.  An audit therefore resolves a
    logical replicate across those immutable directories instead of assuming
    that the first path is authoritative forever.
    """

    candidates = [base] if base.exists() else []

    def retry_number(path: Path) -> int:
        suffix = path.name.removeprefix(f"{base.name}-retry-")
        try:
            return int(suffix)
        except ValueError:
            return 10**9

    candidates.extend(sorted(base.parent.glob(f"{base.name}-retry-*"), key=retry_number))
    return candidates


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


def task_bundle(task: str) -> dict[str, Any]:
    return json.loads((TASKDATA / TASK_FILES[task]).read_text())


def diagnostics() -> dict[tuple[str, int], dict[str, Any]]:
    data = json.loads(DIAGNOSTICS.read_text())
    return {(str(row["task"]), int(row["seed_index"])): row for row in data["landscapes"]}


def base_agent_id(agent_id: str) -> str:
    return agent_id.split("-from-", 1)[0]


def initial_candidate(agent_id: str, n: int = 128) -> str:
    digest = hashlib.sha256(f"{INITIAL_SALT}:{base_agent_id(agent_id)}".encode()).digest()
    bits = "".join(f"{byte:08b}" for byte in digest)
    while len(bits) < n:
        digest = hashlib.sha256(digest).digest()
        bits += "".join(f"{byte:08b}" for byte in digest)
    return bits[:n]


def agent_balance(records: list[dict[str, Any]], budget: int) -> dict[str, Any]:
    counts: defaultdict[str, int] = defaultdict(int)
    for record in records:
        counts[str(record.get("agent_id") or "unknown")] += 1
    values = list(counts.values())
    expected = budget // 8
    return {
        "agent_attempt_counts": json.dumps(dict(sorted(counts.items())), sort_keys=True),
        "agent_attempt_min": min(values, default=0),
        "agent_attempt_max": max(values, default=0),
        "agent_quota_gate": len(counts) == 8 and all(value == expected for value in values),
    }


def mean_hamming(candidates: list[str]) -> float:
    distances = [
        sum(left != right for left, right in zip(candidates[i], candidates[j], strict=True))
        / len(candidates[i])
        for i in range(len(candidates))
        for j in range(i + 1, len(candidates))
    ]
    return statistics.fmean(distances) if distances else 0.0


def latest_diversity(parsed: list[tuple[dict[str, Any], str]], count: int) -> float:
    latest: dict[str, str] = {}
    for record, candidate in parsed[:count]:
        latest[str(record.get("agent_id") or "unknown")] = candidate
    return mean_hamming(list(latest.values()))


def normalized(score: float, reference: dict[str, Any]) -> float:
    baseline = float(reference["random_mean"])
    denominator = float(reference["greedy_reference_score"]) - baseline
    if denominator <= 0:
        raise ValueError("non-positive diagnostic reference gap")
    return (score - baseline) / denominator


def collect(
    run_dir: Path,
    identity: dict[str, Any],
    task: str,
    budget: int,
    references: dict[tuple[str, int], dict[str, Any]],
) -> dict[str, Any]:
    repetition = int(identity["repetition"])
    reference = references[(task, repetition - 1)]
    n = int(reference["n"])
    records = real_records(run_dir)
    parsed: list[tuple[dict[str, Any], str]] = []
    parse_errors: list[str] = []
    initial_errors: list[str] = []
    seen_first: set[str] = set()
    numeric = 0
    invalid = 0
    scores: list[float] = []
    best_progress: list[float] = []
    best = float("-inf")
    seen_candidates: set[str] = set()
    duplicate_candidates = 0
    for record in records:
        commit = str(record.get("commit_hash") or "")
        score = record.get("score")
        if isinstance(score, (int, float)):
            numeric += 1
            value = float(score)
            scores.append(value)
            best = max(best, value)
            best_progress.append(best)
        agent = str(record.get("agent_id") or "unknown")
        try:
            source = source_at(run_dir, commit)
            candidate = legacy.candidate_from_source(source)
            if len(candidate) != n or set(candidate) - {"0", "1"}:
                raise ValueError(f"candidate is not a literal {n}-bit string")
            parsed.append((record, candidate))
            if candidate in seen_candidates:
                duplicate_candidates += 1
            seen_candidates.add(candidate)
            if agent not in seen_first:
                seen_first.add(agent)
                if candidate != initial_candidate(agent, n):
                    initial_errors.append(agent)
        except (OSError, ValueError, SyntaxError, KeyError, TypeError) as exc:
            parse_errors.append(f"{commit}:{exc}")
        if "Invalid candidate:" in str(record.get("feedback") or ""):
            invalid += 1
    final_best = best if scores else 0.0
    auc = (
        statistics.fmean(normalized(value, reference) for value in best_progress)
        if (best_progress)
        else float("-inf")
    )
    row = {
        "task": task,
        "condition": str(identity["condition"]),
        "repetition": repetition,
        "budget": budget,
        "real_attempts": len(records),
        "numeric_scores": numeric,
        "invalid_candidate_count": invalid,
        "parse_error_count": len(parse_errors),
        "parse_errors": ";".join(parse_errors),
        "initial_protocol_error_count": len(initial_errors),
        "initial_protocol_errors": ";".join(initial_errors),
        "best_score": final_best,
        "reference_gain": normalized(final_best, reference),
        "best_so_far_auc_reference": auc,
        "random_z": (
            (final_best - float(reference["random_mean"])) / float(reference["random_sd"])
        ),
        "midpoint_diversity": latest_diversity(parsed, budget // 2),
        "final_diversity": latest_diversity(parsed, budget),
        "unique_candidates": len(seen_candidates),
        "duplicate_candidates": duplicate_candidates,
        "duplicate_candidate_rate": duplicate_candidates / len(parsed) if parsed else 0.0,
        "score_range": max(scores, default=0.0) - min(scores, default=0.0),
        "reference_is_exact": bool(reference["reference_is_exact"]),
        "reference_score": float(reference["greedy_reference_score"]),
        "random_mean": float(reference["random_mean"]),
    }
    row.update(agent_balance(records, budget))
    row.update(behavior_metrics(parsed))
    return row


def integrity(
    run_dir: Path,
    identity: dict[str, Any],
    task: str,
    budget: int,
    row: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    condition = str(identity.get("condition"))
    topology = {
        "global_8": ("1", "false", "1"),
        "partition_4": ("4", "false", "4"),
        "multi_island_2": ("2", "true", "2"),
        "multi_island_4": ("4", "true", "4"),
    }.get(condition)
    values = overrides(identity)
    if topology is None:
        errors.append("unknown topology")
    else:
        every = migration_every(budget)
        expected = {
            "agents.count": "8",
            "agents.runtime": "opencode",
            "agents.model": "mafia/glm-5.2",
            "agents.timeout": str(AGENT_TIMEOUT),
            "agents.sandbox.network": "allowlist",
            "agents.sandbox.allowed_domains": '["api.appintheloop.com"]',
            "agents.runtime_options.role_file": str(ROLE_FILE),
            "agents.heartbeat": heartbeat_for(budget),
            "grader.parallel.max_workers": "4",
            "grader.args.disable_tune": "true",
            "grader.args.seed_index": str(int(identity["repetition"]) - 1),
            "islands.count": topology[0],
            "islands.migration.enabled": topology[1],
            "islands.migration.dest_weighting": "round_robin",
            "islands.migration.every": str(every),
            "islands.migration.rank_window": str(every),
            "islands.migration.max_per_cycle": topology[2],
            "islands.migration.remigration_cooldown": str(every),
            "run.stop.max_real_attempts": str(budget),
            "run.stop.max_real_attempts_per_agent": str(budget // 8),
        }
        for key, expected_value in expected.items():
            if values.get(key) != expected_value:
                errors.append(f"{key}={values.get(key)!r}, expected {expected_value!r}")
    if budget not in BUDGETS:
        errors.append("unregistered budget")
    resolved_path = run_dir / ".coral/config.yaml"
    try:
        resolved = yaml.safe_load(resolved_path.read_text())
        allowed_domains = resolved["agents"]["sandbox"].get("allowed_domains", [])
    except (OSError, TypeError, KeyError, yaml.YAMLError):
        errors.append("resolved config is unreadable")
    else:
        if allowed_domains != list(MODEL_API_DOMAINS):
            errors.append(f"network allowlist={allowed_domains!r}, expected model API only")
    frozen = TASKDATA / TASK_FILES[task]
    private = run_dir / ".coral/private" / TASK_FILES[task]
    if not private.is_file() or private.read_bytes() != frozen.read_bytes():
        errors.append("private replicated landscape bundle mismatch")
    records = real_records(run_dir)
    if len(records) != budget:
        errors.append(f"real attempts={len(records)}, expected {budget}")
    if disallowed_records(run_dir):
        errors.append("disallowed tune/grader-error attempt present")
    stop = load_json(run_dir / ".coral/public/auto_stop.json") or {}
    if stop.get("reason") != "max_real_attempts":
        errors.append(f"auto-stop reason={stop.get('reason')!r}")
    migrations = list(run_dir.glob(".coral/islands/*/notes/migrations/migration_*.md"))
    migration_enabled = condition.startswith("multi_island_")
    if not migration_enabled and migrations:
        errors.append("migration notes in control")
    if migration_enabled and budget >= migration_every(budget) and not migrations:
        errors.append("multi-island cell has no migration event")
    if row["numeric_scores"] != budget:
        errors.append("non-numeric real score present")
    if row["parse_error_count"] > MAX_MALFORMED:
        errors.append(f"candidate parse errors={row['parse_error_count']}")
    if row["invalid_candidate_count"] > MAX_MALFORMED:
        errors.append(f"invalid candidates={row['invalid_candidate_count']}")
    if row["initial_protocol_error_count"]:
        errors.append("topology-invariant initial-candidate protocol failed")
    if not row["agent_quota_gate"]:
        errors.append(
            f"per-agent quota failed: min={row['agent_attempt_min']}, max={row['agent_attempt_max']}"
        )
    return errors


def bootstrap_interval(values: list[float], seed_text: str) -> tuple[float, float]:
    rng = random.Random(int.from_bytes(hashlib.sha256(seed_text.encode()).digest()[:8], "big"))
    samples = sorted(statistics.fmean(rng.choice(values) for _ in values) for _ in range(20_000))
    return samples[500], samples[19_500]


def make_contrasts(
    rows: list[dict[str, Any]],
    repetitions: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    indexed = {
        (row["task"], row["budget"], row["condition"], row["repetition"]): row for row in rows
    }
    output: list[dict[str, Any]] = []
    threshold: int | None = None
    for budget in BUDGETS:
        task_effects: dict[str, dict[int, float]] = {}
        rugged_partition_effect: dict[str, Any] | None = None
        for task in TASKS:
            comparisons = (
                ("multi_island_2", "global_8"),
                (PRIMARY_TREATMENT, "global_8"),
                (PRIMARY_TREATMENT, "partition_4"),
            )
            for treatment, reference in comparisons:
                pairs: defaultdict[str, list[float]] = defaultdict(list)
                random_z_by_repetition: dict[int, float] = {}
                for repetition in range(1, repetitions + 1):
                    left = indexed.get((task, budget, treatment, repetition))
                    right = indexed.get((task, budget, reference, repetition))
                    if left is None or right is None:
                        continue
                    for metric in CONTRAST_METRICS:
                        pairs[metric].append(float(left[metric]) - float(right[metric]))
                    random_z_by_repetition[repetition] = float(left["random_z"]) - float(
                        right["random_z"]
                    )
                if not pairs:
                    continue
                item: dict[str, Any] = {
                    "task": task,
                    "budget": budget,
                    "contrast": f"{treatment}_minus_{reference}",
                    "paired_repetitions": len(pairs["random_z"]),
                    "confirmatory_ready": len(pairs["random_z"]) == 8 and repetitions == 8,
                }
                for metric, values in pairs.items():
                    low, high = bootstrap_interval(
                        values,
                        f"{task}:{budget}:{treatment}:{reference}:{metric}",
                    )
                    item[f"{metric}_difference"] = statistics.fmean(values)
                    item[f"{metric}_ci_low"] = low
                    item[f"{metric}_ci_high"] = high
                item["threshold_rule_passes"] = (
                    item["confirmatory_ready"]
                    and treatment == PRIMARY_TREATMENT
                    and reference == "global_8"
                    and item["random_z_difference"] >= PRACTICAL_DELTA_Z
                    and item["random_z_ci_low"] > 0
                )
                output.append(item)
                if treatment == PRIMARY_TREATMENT and reference == "global_8":
                    task_effects[task] = random_z_by_repetition
                if (
                    task == RUGGED_TASK
                    and treatment == PRIMARY_TREATMENT
                    and reference == "partition_4"
                ):
                    rugged_partition_effect = item

        if set(task_effects) == set(TASKS):
            paired_repetitions = sorted(
                set(task_effects[RUGGED_TASK]) & set(task_effects[SMOOTH_TASK])
            )
            if not paired_repetitions:
                continue
            interaction = [
                task_effects[RUGGED_TASK][repetition] - task_effects[SMOOTH_TASK][repetition]
                for repetition in paired_repetitions
            ]
            low, high = bootstrap_interval(interaction, f"interaction:{budget}")
            ready = len(interaction) == 8 and repetitions == 8
            rugged_row = next(
                row
                for row in output
                if row["task"] == RUGGED_TASK
                and row["budget"] == budget
                and row["contrast"] == f"{PRIMARY_TREATMENT}_minus_global_8"
            )
            passes = (
                ready
                and rugged_row["threshold_rule_passes"]
                and statistics.fmean(interaction) >= PRACTICAL_DELTA_Z
                and low > 0
                and rugged_partition_effect is not None
                and rugged_partition_effect["confirmatory_ready"]
                and rugged_partition_effect["random_z_difference"] > 0
                and rugged_partition_effect["random_z_ci_low"] > 0
            )
            output.append(
                {
                    "task": "rugged_minus_smooth",
                    "budget": budget,
                    "contrast": "difference_in_multi_minus_global",
                    "paired_repetitions": len(interaction),
                    "random_z_difference": statistics.fmean(interaction),
                    "random_z_ci_low": low,
                    "random_z_ci_high": high,
                    "confirmatory_ready": ready,
                    "threshold_rule_passes": passes,
                }
            )
            if passes and threshold is None:
                threshold = budget
    return output, {
        "registered_repetitions": 8,
        "practical_delta_random_z": PRACTICAL_DELTA_Z,
        "primary_treatment": PRIMARY_TREATMENT,
        "earliest_full_multi_island_threshold": threshold,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-root",
        type=Path,
        default=Path("/var/tmp/coral-institutions-results/nk-threshold-v2"),
    )
    parser.add_argument("--tasks", nargs="+", choices=TASKS, default=list(TASKS))
    parser.add_argument("--conditions", nargs="+", choices=CONDITIONS, default=list(CONDITIONS))
    parser.add_argument("--budgets", nargs="+", type=int, default=list(BUDGETS))
    parser.add_argument("--repetitions", type=int, default=8)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "threshold_v2_analysis")
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if any(budget not in BUDGETS for budget in args.budgets):
        raise SystemExit("analysis requested an unregistered threshold-v2 budget")
    references = diagnostics()
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    superseded: list[dict[str, Any]] = []
    expected = 0
    for budget in args.budgets:
        for task in args.tasks:
            for condition in args.conditions:
                for repetition in range(1, args.repetitions + 1):
                    expected += 1
                    base_run_dir = (
                        args.results_root.resolve()
                        / f"budget-{budget}"
                        / task
                        / condition
                        / f"rep-{repetition:02d}"
                    )
                    candidates = existing_run_dirs(base_run_dir)
                    if not candidates:
                        failures.append(
                            {
                                "budget": budget,
                                "task": task,
                                "condition": condition,
                                "repetition": repetition,
                                "reasons": ["missing run"],
                            }
                        )
                        continue
                    accepted_row: dict[str, Any] | None = None
                    rejected: list[dict[str, Any]] = []
                    for run_dir in candidates:
                        identity = load_json(run_dir / "operator-command.json")
                        if identity is None:
                            rejected.append(
                                {"run_dir": str(run_dir), "reasons": ["missing identity"]}
                            )
                            continue
                        row = collect(run_dir, identity, task, budget, references)
                        reasons = integrity(run_dir, identity, task, budget, row)
                        if reasons:
                            rejected.append(
                                {
                                    "run_dir": str(run_dir),
                                    "reasons": reasons,
                                    "observed": row,
                                }
                            )
                            continue
                        row["run_dir"] = str(run_dir)
                        row["superseded_run_count"] = len(rejected)
                        row["superseded_run_dirs"] = ";".join(
                            item["run_dir"] for item in rejected
                        )
                        accepted_row = row
                        superseded.extend(rejected)
                        break
                    if accepted_row is None:
                        failures.append(
                            {
                                "budget": budget,
                                "task": task,
                                "condition": condition,
                                "repetition": repetition,
                                "reasons": ["no valid base or retry run"],
                                "candidate_runs": rejected,
                            }
                        )
                    else:
                        rows.append(accepted_row)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "runs.csv", rows)
    contrast_rows, threshold = make_contrasts(rows, args.repetitions)
    write_csv(output / "contrasts.csv", contrast_rows)
    (output / "threshold.json").write_text(json.dumps(threshold, indent=2) + "\n")
    audit = {
        "schema_version": 2,
        "primary_metric": "final best random-baseline z-score",
        "primary_contrast": "multi_island_4 minus global_8 paired within held-out seed",
        "accepted_rows": len(rows),
        "expected_rows": expected,
        "integrity_failures": failures,
        "superseded_invalid_runs": superseded,
    }
    (output / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(f"Audited {len(rows)}/{expected} threshold-v2 cells; failures={len(failures)}")
    if failures and not args.allow_incomplete:
        raise SystemExit(f"threshold-v2 matrix incomplete; see {output / 'audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
