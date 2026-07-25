#!/usr/bin/env python3
"""Audit Circle Packing topology cells and compute preregistered contrasts."""

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
import tokenize
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from experiments.multi_island import analyze as common
from experiments.multi_island.isolation_audit import isolation_gate
from experiments.multi_island_circle.run_circle import (
    AGENT_TIMEOUT,
    BUDGETS,
    CONDITIONS,
    EVALUATION_TIMEOUT,
    GRADER_TIMEOUT,
    MIGRATION_EVERY,
    MODEL_API_DOMAINS,
    ROLE_FILE,
    TASK_NAME,
    heartbeat_for,
)
from experiments.multi_island_hard.analyze_threshold_v2 import existing_run_dirs

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
SEED_SOURCE = REPO_ROOT / "examples/math/circle_packing/seed/initial_program.py"
SEED_SCORE = 0.3641018935
PRACTICAL_SCORE_DELTA = 0.01
REGISTERED_REPETITIONS = 8
SOURCE_FILE = "initial_program.py"
CONTRAST_METRICS = (
    "final_best_score",
    "gain_over_seed",
    "best_so_far_auc",
    "latest_source_diversity",
    "null_rate",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-root",
        type=Path,
        default=Path("/var/tmp/coral-institutions-results/circle-packing-v1"),
    )
    parser.add_argument("--budgets", nargs="+", type=int, default=list(BUDGETS))
    parser.add_argument("--conditions", nargs="+", choices=CONDITIONS, default=list(CONDITIONS))
    parser.add_argument("--repetitions", type=int, default=REGISTERED_REPETITIONS)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "analysis")
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


def overrides(identity: dict[str, Any]) -> dict[str, str]:
    return {
        item.split("=", 1)[0]: item.split("=", 1)[1]
        for item in identity.get("command", [])
        if isinstance(item, str) and "=" in item
    }


def base_agent_id(agent_id: str) -> str:
    return agent_id.split("-from-", 1)[0]


def source_tokens(source: str) -> tuple[str, ...]:
    ast.parse(source)
    ignored = {
        tokenize.ENCODING,
        tokenize.ENDMARKER,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.NEWLINE,
        tokenize.NL,
        tokenize.COMMENT,
    }
    return tuple(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type not in ignored
    )


def source_shingles(tokens: tuple[str, ...], width: int = 5) -> set[tuple[str, ...]]:
    if len(tokens) < width:
        return {tokens} if tokens else set()
    return {tokens[index : index + width] for index in range(len(tokens) - width + 1)}


def jaccard(left: set[Any], right: set[Any]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def mean_pairwise_distance(values: list[set[Any]]) -> float:
    distances = [
        1.0 - jaccard(values[index], values[other])
        for index in range(len(values))
        for other in range(index + 1, len(values))
    ]
    return statistics.fmean(distances) if distances else 0.0


def strategy_labels(source: str) -> tuple[str, ...]:
    text = source.lower()
    patterns = {
        "differential_evolution": "differential_evolution",
        "basin_hopping": "basinhopping",
        "scipy_minimize": "minimize(",
        "slsqp": "slsqp",
        "linear_program": "linprog",
        "annealing": "anneal",
        "force_relaxation": "force",
        "grid_or_lattice": "grid",
        "ring_constructor": "ring",
        "random_restart": "random" if "restart" in text else "multi_start",
    }
    return tuple(sorted(label for label, needle in patterns.items() if needle in text))


def forbidden_candidate_io(source: str) -> list[str]:
    """Detect integrity-sensitive I/O unavailable to an honest participant.

    Candidate Python executes in the task subprocess, so this source audit is
    required in addition to the agent sandbox until the example grader gains a
    general untrusted-code namespace.
    """

    reasons: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    network_modules = {"requests", "httpx", "socket", "urllib", "ftplib"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] in network_modules:
                    reasons.add(f"network import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".", 1)[0] in network_modules:
            reasons.add(f"network import {node.module}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.lower()
            if "/var/tmp/coral-institutions-results" in value:
                reasons.add("result-directory path literal")
            if ".coral/private" in value:
                reasons.add("grader-private path literal")
            if "http://" in value or "https://" in value:
                reasons.add("URL literal")
            if "curl " in value or "wget " in value:
                reasons.add("external retrieval command")
    return sorted(reasons)


def record_origin(record: dict[str, Any]) -> str:
    metadata = record.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    return str(metadata.get("origin_island_id") or metadata.get("island_id") or "global")


def collect(run_dir: Path, identity: dict[str, Any], budget: int) -> dict[str, Any]:
    records, grader_errors, tune_attempts, tune_violations = common.attempt_records(run_dir)
    sources: list[tuple[dict[str, Any], str, set[tuple[str, ...]], str]] = []
    source_errors: list[str] = []
    scored_source_errors: list[str] = []
    forbidden: list[str] = []
    scores: list[float] = []
    best = SEED_SCORE
    best_commit = "seed"
    best_sequence = 0
    best_progress: list[float] = []
    fingerprints_seen: defaultdict[str, set[str]] = defaultdict(set)
    duplicate_sources = 0
    cross_agent_duplicates = 0
    near_foreign_reuses = 0
    prior_sources: list[tuple[str, set[tuple[str, ...]]]] = []

    for sequence, record in enumerate(records, start=1):
        commit = str(record.get("commit_hash") or "")
        agent = base_agent_id(str(record.get("agent_id") or "unknown"))
        score = record.get("score")
        numeric = isinstance(score, (int, float)) and math.isfinite(float(score))
        if numeric:
            value = float(score)
            scores.append(value)
            if value > best:
                best = value
                best_commit = commit
                best_sequence = sequence
        best_progress.append(best)
        try:
            source = common.git_source(run_dir, commit, SOURCE_FILE)
            tokens = source_tokens(source)
            shingles = source_shingles(tokens)
            fingerprint = hashlib.sha256(repr(tokens).encode()).hexdigest()
            labels = ";".join(strategy_labels(source))
            sources.append((record, source, shingles, labels))
            prior_agents = fingerprints_seen[fingerprint]
            if prior_agents:
                duplicate_sources += 1
                if agent not in prior_agents:
                    cross_agent_duplicates += 1
            fingerprints_seen[fingerprint].add(agent)
            if any(
                prior_agent != agent and jaccard(shingles, prior_shingles) >= 0.90
                for prior_agent, prior_shingles in prior_sources
            ):
                near_foreign_reuses += 1
            prior_sources.append((agent, shingles))
            forbidden.extend(f"{commit}:{reason}" for reason in forbidden_candidate_io(source))
        except (OSError, RuntimeError, SyntaxError, tokenize.TokenError) as exc:
            source_errors.append(f"{commit}:{exc}")
            if numeric:
                scored_source_errors.append(f"{commit}:{exc}")

    latest: dict[str, tuple[set[tuple[str, ...]], str]] = {}
    counts: defaultdict[str, int] = defaultdict(int)
    for record in records:
        counts[base_agent_id(str(record.get("agent_id") or "unknown"))] += 1
    last_origin: dict[str, str] = {}
    last_shingles: dict[str, set[tuple[str, ...]]] = {}
    own_best: defaultdict[str, float] = defaultdict(lambda: SEED_SCORE)
    origin_best: defaultdict[str, float] = defaultdict(lambda: SEED_SCORE)
    migrated_agents: set[str] = set()
    post_migration_attempts = 0
    destination_improvements = 0
    destination_gains: list[float] = []
    carried_continuities: list[float] = []

    for record, _source, shingles, labels in sources:
        agent = base_agent_id(str(record.get("agent_id") or "unknown"))
        origin = record_origin(record)
        score = record.get("score")
        numeric = isinstance(score, (int, float)) and math.isfinite(float(score))
        previous_origin = last_origin.get(agent)
        just_migrated = previous_origin is not None and previous_origin != origin
        if just_migrated:
            migrated_agents.add(agent)
            if agent in last_shingles:
                carried_continuities.append(jaccard(last_shingles[agent], shingles))
        if agent in migrated_agents:
            post_migration_attempts += 1
            if numeric and float(score) > origin_best[origin]:
                destination_improvements += 1
                destination_gains.append(float(score) - origin_best[origin])
        if numeric:
            own_best[agent] = max(own_best[agent], float(score))
            origin_best[origin] = max(origin_best[origin], float(score))
        last_origin[agent] = origin
        last_shingles[agent] = shingles
        latest[agent] = (shingles, labels)

    expected_per_agent = budget // 4
    count_values = list(counts.values())
    attempt_times = [
        datetime.fromisoformat(str(record.get("timestamp"))).timestamp()
        for record in records
        if record.get("timestamp")
    ]
    migration_notes = sorted(
        run_dir.glob(".coral/islands/*/notes/migrations/migration_*.md"),
        key=lambda path: (path.stat().st_mtime, str(path)),
    )
    migration_ticks = [
        sum(timestamp <= note.stat().st_mtime for timestamp in attempt_times)
        for note in migration_notes
    ]
    latest_labels = sorted({label for _shingles, labels in latest.values() for label in labels.split(";") if label})
    row = {
        "task": TASK_NAME,
        "condition": str(identity["condition"]),
        "repetition": int(identity["repetition"]),
        "budget": budget,
        "real_attempts": len(records),
        "numeric_scores": len(scores),
        "null_scores": len(records) - len(scores),
        "null_rate": (len(records) - len(scores)) / len(records) if records else 0.0,
        "grader_errors": grader_errors,
        "tune_attempts": tune_attempts,
        "tune_protocol_violations": tune_violations,
        "final_best_score": best,
        "gain_over_seed": best - SEED_SCORE,
        "best_so_far_auc": statistics.fmean(best_progress) if best_progress else SEED_SCORE,
        "best_commit": best_commit,
        "time_to_best": best_sequence,
        "score_range": max(scores, default=SEED_SCORE) - min(scores, default=SEED_SCORE),
        "parsed_sources": len(sources),
        "source_error_count": len(source_errors),
        "source_errors": ";".join(source_errors),
        "scored_source_error_count": len(scored_source_errors),
        "forbidden_candidate_io_count": len(forbidden),
        "forbidden_candidate_io": ";".join(forbidden),
        "unique_source_fingerprints": len(fingerprints_seen),
        "duplicate_sources": duplicate_sources,
        "cross_agent_duplicate_sources": cross_agent_duplicates,
        "near_foreign_source_reuses": near_foreign_reuses,
        "latest_source_diversity": mean_pairwise_distance(
            [value[0] for value in latest.values()]
        ),
        "latest_strategy_labels": ";".join(latest_labels),
        "latest_strategy_label_count": len(latest_labels),
        "migration_notes": len(migration_notes),
        "migration_ticks": json.dumps(migration_ticks),
        "migrated_agents": len(migrated_agents),
        "post_migration_attempts": post_migration_attempts,
        "post_migration_destination_improvements": destination_improvements,
        "max_post_migration_destination_gain": max(destination_gains, default=0.0),
        "mean_migrant_source_continuity": statistics.fmean(carried_continuities)
        if carried_continuities
        else 0.0,
        "agent_attempt_counts": json.dumps(dict(sorted(counts.items())), sort_keys=True),
        "agent_attempt_min": min(count_values, default=0),
        "agent_attempt_max": max(count_values, default=0),
        "agent_quota_gate": len(counts) == 4
        and all(value == expected_per_agent for value in count_values),
    }
    return row


def integrity(
    run_dir: Path,
    identity: dict[str, Any],
    budget: int,
    row: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    condition = str(identity.get("condition"))
    topology = {
        "global": ("1", "false"),
        "partition": ("2", "false"),
        "multi_island": ("2", "true"),
    }.get(condition)
    values = overrides(identity)
    if topology is None:
        errors.append("unknown topology")
    else:
        expected = {
            "agents.count": "4",
            "agents.runtime": "opencode",
            "agents.model": "mafia/glm-5.2",
            "agents.runtime_options.role_file": str(ROLE_FILE),
            "agents.heartbeat": heartbeat_for(budget),
            "agents.timeout": str(AGENT_TIMEOUT),
            "agents.sandbox.network": "allowlist",
            "agents.sandbox.allowed_domains": '["api.appintheloop.com"]',
            "grader.parallel.max_workers": "2",
            "grader.args.disable_tune": "true",
            "grader.timeout": str(GRADER_TIMEOUT),
            "grader.args.evaluation_timeout": str(EVALUATION_TIMEOUT),
            "grader.args.harden_candidate": "true",
            "islands.count": topology[0],
            "islands.migration.enabled": topology[1],
            "islands.migration.every": str(MIGRATION_EVERY),
            "islands.migration.rank_window": str(MIGRATION_EVERY),
            "islands.migration.max_per_cycle": "2",
            "islands.migration.remigration_cooldown": str(MIGRATION_EVERY),
            "islands.migration.dest_weighting": "round_robin",
            "run.stop.max_real_attempts": str(budget),
            "run.stop.max_real_attempts_per_agent": str(budget // 4),
        }
        for key, expected_value in expected.items():
            if values.get(key) != expected_value:
                errors.append(f"{key}={values.get(key)!r}, expected {expected_value!r}")
    if budget not in BUDGETS:
        errors.append("unregistered budget")
    try:
        resolved = yaml.safe_load((run_dir / ".coral/config.yaml").read_text())
        allowed_domains = resolved["agents"]["sandbox"].get("allowed_domains", [])
    except (OSError, TypeError, KeyError, yaml.YAMLError):
        errors.append("resolved config is unreadable")
    else:
        if allowed_domains != list(MODEL_API_DOMAINS):
            errors.append(f"network allowlist={allowed_domains!r}, expected model API only")
    try:
        if (run_dir / "repo" / SOURCE_FILE).read_bytes() != SEED_SOURCE.read_bytes():
            errors.append("seed source differs from frozen Circle Packing seed")
    except OSError:
        errors.append("frozen seed source is unreadable")
    if row["real_attempts"] != budget:
        errors.append(f"real attempts={row['real_attempts']}, expected {budget}")
    if row["grader_errors"]:
        errors.append(f"grader errors={row['grader_errors']}")
    if row["tune_protocol_violations"]:
        errors.append(f"tune protocol violations={row['tune_protocol_violations']}")
    stop = common.load_json(run_dir / ".coral/public/auto_stop.json") or {}
    if stop.get("reason") != "max_real_attempts":
        errors.append(f"auto-stop reason={stop.get('reason')!r}")
    if condition != "multi_island" and row["migration_notes"]:
        errors.append("migration notes in non-migration control")
    if condition == "multi_island" and budget >= MIGRATION_EVERY:
        if not row["migration_notes"]:
            errors.append("multi-island cell has no migration event")
        if not row["post_migration_attempts"]:
            errors.append("multi-island cell has no real post-migration attempt")
    if row["scored_source_error_count"]:
        errors.append(f"scored source parse errors={row['scored_source_error_count']}")
    if row["forbidden_candidate_io_count"]:
        errors.append("candidate source attempted forbidden host/network I/O")
    isolated, isolation_violations = isolation_gate(run_dir)
    row["isolation_trace_gate"] = isolated
    row["isolation_trace_violation_count"] = len(isolation_violations)
    row["isolation_trace_violations"] = ";".join(isolation_violations)
    if not isolated:
        errors.append("cross-island information access in runtime trace")
    if not row["agent_quota_gate"]:
        errors.append(
            f"per-agent quota failed: min={row['agent_attempt_min']}, "
            f"max={row['agent_attempt_max']}"
        )
    return errors


def bootstrap_interval(values: list[float], seed: str) -> tuple[float, float]:
    if not values:
        return float("nan"), float("nan")
    rng = random.Random(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big"))
    samples = sorted(
        statistics.fmean(rng.choice(values) for _ in values) for _ in range(20_000)
    )
    return samples[500], samples[19_500]


def make_contrasts(
    rows: list[dict[str, Any]], repetitions: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    indexed = {
        (int(row["budget"]), str(row["condition"]), int(row["repetition"])): row
        for row in rows
    }
    output: list[dict[str, Any]] = []
    passing: dict[tuple[int, str], bool] = {}
    comparisons = (
        ("multi_island", "partition"),
        ("multi_island", "global"),
        ("partition", "global"),
    )
    for budget in BUDGETS:
        for treatment, reference in comparisons:
            pairs: defaultdict[str, list[float]] = defaultdict(list)
            compliance: list[bool] = []
            for repetition in range(1, repetitions + 1):
                left = indexed.get((budget, treatment, repetition))
                right = indexed.get((budget, reference, repetition))
                if left is None or right is None:
                    continue
                for metric in CONTRAST_METRICS:
                    pairs[metric].append(float(left[metric]) - float(right[metric]))
                if treatment == "multi_island":
                    compliance.append(
                        int(left["migration_notes"]) > 0
                        and int(left["post_migration_attempts"]) > 0
                    )
            if not pairs:
                continue
            item: dict[str, Any] = {
                "budget": budget,
                "contrast": f"{treatment}_minus_{reference}",
                "paired_repetitions": len(pairs["final_best_score"]),
            }
            for metric, values in pairs.items():
                low, high = bootstrap_interval(values, f"circle:{budget}:{treatment}:{reference}:{metric}")
                item[f"{metric}_difference"] = statistics.fmean(values)
                item[f"{metric}_ci_low"] = low
                item[f"{metric}_ci_high"] = high
            confirmatory = repetitions == REGISTERED_REPETITIONS and len(
                pairs["final_best_score"]
            ) == REGISTERED_REPETITIONS
            passes = (
                treatment == "multi_island"
                and confirmatory
                and item["final_best_score_difference"] >= PRACTICAL_SCORE_DELTA
                and item["final_best_score_ci_low"] > 0
                and all(compliance)
            )
            item["all_multi_cells_have_post_migration_work"] = all(compliance)
            item["confirmatory_ready"] = confirmatory
            item["contrast_rule_passes"] = passes
            if treatment == "multi_island":
                passing[(budget, reference)] = passes
            output.append(item)
    earliest = next(
        (
            budget
            for budget in BUDGETS
            if passing.get((budget, "partition"), False)
            and passing.get((budget, "global"), False)
        ),
        None,
    )
    return output, {
        "registered_repetitions": REGISTERED_REPETITIONS,
        "practical_score_delta": PRACTICAL_SCORE_DELTA,
        "primary_contrast": "multi_island_minus_partition",
        "secondary_contrast": "multi_island_minus_global",
        "earliest_supported_multi_island_threshold": earliest,
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


def main() -> int:
    args = parse_args()
    if any(budget not in BUDGETS for budget in args.budgets):
        raise SystemExit("analysis requested an unregistered Circle Packing budget")
    if args.repetitions < 1:
        raise SystemExit("repetitions must be positive")
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    superseded: list[dict[str, Any]] = []
    expected = 0
    for budget in args.budgets:
        for condition in args.conditions:
            for repetition in range(1, args.repetitions + 1):
                expected += 1
                base_run_dir = (
                    args.results_root.resolve()
                    / f"budget-{budget}"
                    / TASK_NAME
                    / condition
                    / f"rep-{repetition:02d}"
                )
                candidates = existing_run_dirs(base_run_dir)
                if not candidates:
                    failures.append(
                        {
                            "budget": budget,
                            "condition": condition,
                            "repetition": repetition,
                            "reasons": ["missing run"],
                        }
                    )
                    continue
                accepted: dict[str, Any] | None = None
                rejected: list[dict[str, Any]] = []
                for run_dir in candidates:
                    identity = common.load_json(run_dir / "operator-command.json")
                    if identity is None:
                        rejected.append(
                            {"run_dir": str(run_dir), "reasons": ["missing identity"]}
                        )
                        continue
                    row = collect(run_dir, identity, budget)
                    reasons = integrity(run_dir, identity, budget, row)
                    if reasons:
                        rejected.append(
                            {"run_dir": str(run_dir), "reasons": reasons, "observed": row}
                        )
                        continue
                    row["run_dir"] = str(run_dir)
                    row["superseded_run_count"] = len(rejected)
                    row["superseded_run_dirs"] = ";".join(
                        item["run_dir"] for item in rejected
                    )
                    accepted = row
                    superseded.extend(rejected)
                    break
                if accepted is None:
                    failures.append(
                        {
                            "budget": budget,
                            "condition": condition,
                            "repetition": repetition,
                            "reasons": ["no valid base or retry run"],
                            "candidate_runs": rejected,
                        }
                    )
                else:
                    rows.append(accepted)

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "runs.csv", rows)
    contrasts, threshold = make_contrasts(rows, args.repetitions)
    write_csv(output / "contrasts.csv", contrasts)
    (output / "threshold.json").write_text(json.dumps(threshold, indent=2) + "\n")
    audit = {
        "schema_version": 1,
        "primary_metric": "final best valid normalized Circle Packing score",
        "accepted_rows": len(rows),
        "expected_rows": expected,
        "integrity_failures": failures,
        "superseded_invalid_runs": superseded,
    }
    (output / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(f"Audited {len(rows)}/{expected} Circle Packing cells; failures={len(failures)}")
    if failures and not args.allow_incomplete:
        raise SystemExit(f"Circle Packing matrix incomplete; see {output / 'audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
