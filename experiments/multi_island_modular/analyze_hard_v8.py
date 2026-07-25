#!/usr/bin/env python3
"""Audit and summarize the v8 certified-composition threshold matrix."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from experiments.multi_island.isolation_audit import isolation_gate

ROOT = Path(__file__).resolve().parent
GRADER_SRC = ROOT / "tasks/hard_active_modular_landscape_v8/grader/src"
sys.path.insert(0, str(GRADER_SRC))
from hard_active_modular_landscape_v8_grader.grader import (  # noqa: E402
    ACTIVE_WEIGHT,
    ASSEMBLY_WEIGHT,
    BLOCKS,
    artifact_exact_count,
    certificate_for,
    certified_modules,
    parse_candidate_source,
    target_bits,
)

from experiments.multi_island_modular import analyze_hard_v4 as common  # noqa: E402
from experiments.multi_island_modular.run_hard_v8 import (  # noqa: E402
    MODEL_API_DOMAINS,
    heartbeat_for,
)
from experiments.multi_island_modular.simulate_hard_v8 import (  # noqa: E402
    BUDGETS,
    MIGRATION_EVERY,
    MODULE_COST,
)

common = importlib.reload(common)

TASKDATA = ROOT / "tasks/hard_active_modular_landscape_v8/taskdata/hard_v8_seed_bundle.json"
SEED_BUNDLE_FILENAME = "hard_v8_seed_bundle.json"
ROLE_FILE = ROOT / "hard_v8_eval_protocol.md"
TASKS = ("smooth_certified_v8", "rugged_certified_v8")
CONDITIONS = ("global_8", "partition", "multi_island")
MAX_MALFORMED_ATTEMPTS = 1
MIN_MODULE_COVERAGE = 8
MIN_ISLAND_COVERAGE = 4
AGENT_LANE_INDEX = {
    "captain-nemo": 0,
    "captain-ahab": 1,
    "jack-sparrow": 2,
    "davy-jones": 3,
    "long-john-silver": 4,
    "sinbad-the-sailor": 5,
    "horatio-hornblower": 6,
    "jack-aubrey": 7,
}


def mode_for(task: str) -> str:
    if task == "smooth_certified_v8":
        return "smooth"
    if task == "rugged_certified_v8":
        return "rugged"
    raise ValueError(f"unknown v8 task {task!r}")


def bundle() -> dict[str, Any]:
    return json.loads(TASKDATA.read_text())


def eval_payload(record: dict[str, Any]) -> dict[str, Any] | None:
    text = str(record.get("feedback") or "")
    marker = "eval:"
    start = text.find(marker)
    if start < 0:
        return None
    decoder = json.JSONDecoder()
    try:
        payload, _ = decoder.raw_decode(text[start + len(marker) :].lstrip())
    except (json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def record_origin(record: dict[str, Any]) -> str:
    metadata = record.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    return str(metadata.get("origin_island_id") or common.record_island(record))


def base_agent_id(agent_id: str) -> str:
    return agent_id.split("-from-", 1)[0]


def lane_index(agent_id: str) -> int:
    base = base_agent_id(agent_id)
    if base in AGENT_LANE_INDEX:
        return AGENT_LANE_INDEX[base]
    return int.from_bytes(hashlib.sha256(base.encode()).digest()[:2], "big") % 8


def search_query_error(
    *,
    agent_id: str,
    active: int,
    bits: str,
    carried: set[int],
    active_score: float | None,
    exact: bool,
    states: dict[tuple[str, int], dict[str, Any]],
) -> str | None:
    """Validate probes against the incumbent, not the preceding query.

    A rejected coordinate probe is followed by a query that both restores the
    rejected bit and flips the next bit.  Those two submitted strings are two
    bits apart even though both are legal one-coordinate probes of the same
    incumbent.  Tracking the incumbent also lets the audit distinguish that
    registered operator from multi-bit group testing.
    """

    if active in carried or exact:
        return None
    base = base_agent_id(agent_id)
    key = (base, active)
    if active % 8 != lane_index(base):
        return f"{base}:searched-unowned-module-{active}"
    state = states.get(key)
    if state is None:
        if bits != "0" * len(bits):
            return f"{base}:module-{active}-did-not-start-at-zero"
        if active_score is not None:
            states[key] = {
                "incumbent": bits,
                "score": active_score,
                "probed": set(),
            }
        return None
    incumbent = str(state["incumbent"])
    changed = [
        index
        for index, (left, right) in enumerate(zip(incumbent, bits, strict=True))
        if left != right
    ]
    if len(changed) != 1:
        return f"{base}:module-{active}-changed-{len(changed)}-coordinates-from-incumbent"
    coordinate = changed[0]
    probed = state["probed"]
    if coordinate in probed:
        return f"{base}:module-{active}-repeated-coordinate-{coordinate}"
    probed.add(coordinate)
    if active_score is not None and active_score > float(state["score"]):
        state["incumbent"] = bits
        state["score"] = active_score
    return None


def agent_balance(records: list[dict[str, Any]], budget: int) -> dict[str, Any]:
    counts: defaultdict[str, int] = defaultdict(int)
    for record in records:
        counts[str(record.get("agent_id") or "unknown")] += 1
    values = list(counts.values())
    expected = budget // 8 if budget % 8 == 0 else -1
    return {
        "agent_attempt_counts": json.dumps(dict(sorted(counts.items())), sort_keys=True),
        "agent_attempt_min": min(values, default=0),
        "agent_attempt_max": max(values, default=0),
        "agent_balance_ratio": min(values, default=0) / max(values, default=1),
        "agent_quota_gate": len(counts) == 8 and all(value == expected for value in values),
    }


def collect(
    run_dir: Path,
    identity: dict[str, Any],
    task: str,
    budget: int,
) -> dict[str, Any]:
    repetition = int(identity["repetition"])
    seed = str(bundle()["seeds"][repetition - 1])
    mode = mode_for(task)
    records = common.real_records(run_dir)

    discovered: set[int] = set()
    discovery_origins: defaultdict[int, set[str]] = defaultdict(set)
    active_by_origin: defaultdict[str, set[int]] = defaultdict(set)
    best_by_origin: defaultdict[str, int] = defaultdict(int)
    transferred_blocks: set[int] = set()
    transferred_destinations: set[tuple[int, str]] = set()
    transfer_events = 0
    first_transfer_eval: int | None = None
    duplicate_queries = 0
    cross_island_duplicate_queries = 0
    seen_queries: defaultdict[tuple[int, str], set[str]] = defaultdict(set)
    parse_errors: list[str] = []
    feedback_errors: list[str] = []
    search_errors: list[str] = []
    smooth_search_states: dict[tuple[str, int], dict[str, Any]] = {}
    best_certified = 0
    best_actual = 0
    best_commit = ""
    numeric_scores = 0
    invalid_candidates = 0

    for sequence, record in enumerate(records, start=1):
        commit = str(record.get("commit_hash") or "")
        score = record.get("score")
        numeric_scores += int(isinstance(score, (int, float)))
        payload = eval_payload(record)
        if payload is None:
            feedback_errors.append(f"{commit}:missing-payload")
        elif "invalid_candidate" in payload:
            invalid_candidates += 1
            if score != 0.0:
                feedback_errors.append(f"{commit}:invalid-nonzero")
        try:
            source = common.source_at(run_dir, commit)
            modules, active, certificates = parse_candidate_source(source, f"{commit}:candidate.py")
            carried = set(certified_modules(seed, mode, modules, certificates))
        except (OSError, ValueError, SyntaxError, KeyError, TypeError) as exc:
            parse_errors.append(f"{commit}:{exc}")
            continue

        origin = record_origin(record)
        active_by_origin[origin].add(active)
        bits = modules[active]
        if mode == "smooth":
            active_value = payload.get("active_score") if payload is not None else None
            search_error = search_query_error(
                agent_id=str(record.get("agent_id") or "unknown"),
                active=active,
                bits=bits,
                carried=carried,
                active_score=(
                    float(active_value) if isinstance(active_value, (int, float)) else None
                ),
                exact=bits == target_bits(seed, active),
                states=smooth_search_states,
            )
            if search_error is not None:
                search_errors.append(f"{commit}:{search_error}")
        query = (active, bits)
        if seen_queries[query]:
            duplicate_queries += 1
            if origin not in seen_queries[query]:
                cross_island_duplicate_queries += 1
        seen_queries[query].add(origin)

        tested = (
            payload is not None
            and payload.get("tested") is True
            and bits == target_bits(seed, active)
        )
        if tested:
            expected_token = certificate_for(seed, mode, active, bits)
            if payload.get("certificate") != expected_token:
                feedback_errors.append(f"{commit}:bad-issued-certificate")
            carried.add(active)

        foreign = {
            block
            for block in carried
            if discovery_origins.get(block) and origin not in discovery_origins[block]
        }
        new_destinations = {
            (block, origin) for block in foreign if (block, origin) not in transferred_destinations
        }
        if new_destinations:
            transfer_events += 1
            transferred_destinations.update(new_destinations)
            transferred_blocks.update(block for block, _ in new_destinations)
            if first_transfer_eval is None:
                first_transfer_eval = sequence

        actual = artifact_exact_count(modules, seed=seed)
        if len(carried) > best_certified:
            best_certified = len(carried)
            best_commit = commit
        best_actual = max(best_actual, actual)
        best_by_origin[origin] = max(best_by_origin[origin], len(carried))

        if payload is not None and "invalid_candidate" not in payload:
            if payload.get("active_module") != active:
                feedback_errors.append(f"{commit}:wrong-active-module")
            if payload.get("verified_count") != len(carried):
                feedback_errors.append(f"{commit}:wrong-verified-count")
            active_value = payload.get("active_score")
            if isinstance(active_value, (int, float)) and isinstance(score, (int, float)):
                expected_score = ACTIVE_WEIGHT * float(active_value) + ASSEMBLY_WEIGHT * len(
                    carried
                ) / BLOCKS
                if abs(float(score) - expected_score) > 1e-7:
                    feedback_errors.append(f"{commit}:aggregate-score-mismatch")

        if tested:
            discovered.add(active)
            discovery_origins[active].add(origin)

    island_coverage = {key: len(value) for key, value in sorted(active_by_origin.items())}
    multi_scope = str(identity["condition"]) != "global_8"
    coverage_gate = len({block for values in active_by_origin.values() for block in values}) >= (
        MIN_MODULE_COVERAGE
    ) and (
        not multi_scope
        or len(island_coverage) >= 2
        and min(island_coverage.values(), default=0) >= MIN_ISLAND_COVERAGE
    )
    scores = [
        float(record["score"])
        for record in records
        if isinstance(record.get("score"), (int, float))
    ]
    row = {
        "task": task,
        "condition": str(identity["condition"]),
        "repetition": repetition,
        "budget": budget,
        "real_attempts": len(records),
        "numeric_scores": numeric_scores,
        "score_range": max(scores, default=0.0) - min(scores, default=0.0),
        "best_submitted_certified_blocks": best_certified,
        "best_submitted_actual_exact_blocks": best_actual,
        "best_submitted_certified_fraction": best_certified / BLOCKS,
        "best_submitted_commit": best_commit,
        "global_discovered_blocks": len(discovered),
        "assembly_gap": len(discovered) - best_certified,
        "best_by_submission_island": json.dumps(dict(sorted(best_by_origin.items()))),
        "transferred_blocks": len(transferred_blocks),
        "transfer_events": transfer_events,
        "first_transfer_eval": first_transfer_eval,
        "module_coverage": len(
            {block for values in active_by_origin.values() for block in values}
        ),
        "origin_island_coverage": json.dumps(island_coverage, sort_keys=True),
        "coverage_gate": coverage_gate,
        "unique_queries": len(seen_queries),
        "duplicate_queries": duplicate_queries,
        "duplicate_query_rate": duplicate_queries / len(records) if records else 0.0,
        "cross_island_duplicate_queries": cross_island_duplicate_queries,
        "invalid_candidate_count": invalid_candidates,
        "parse_error_count": len(parse_errors),
        "parse_errors": ";".join(parse_errors),
        "feedback_error_count": len(feedback_errors),
        "feedback_errors": ";".join(feedback_errors),
        "search_protocol_error_count": len(search_errors),
        "search_protocol_errors": ";".join(search_errors),
        # Compatibility aliases for prior modular audit tables. The aliases
        # deliberately distinguish feasible submitted assembly from pooling.
        "best_assembled_score": best_certified / BLOCKS,
        "best_tested_blocks": best_certified,
        "final_known_blocks": len(discovered),
        "pooled_assembled_score": len(discovered) / BLOCKS,
        "pooled_tested_blocks": len(discovered),
    }
    row.update(agent_balance(records, budget))
    return row


def integrity(
    run_dir: Path,
    identity: dict[str, Any],
    task: str,
    budget: int,
    row: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    mode = mode_for(task)
    condition = str(identity.get("condition"))
    values = common.overrides(identity)
    topology = {
        "global_8": ("1", "false"),
        "partition": ("2", "false"),
        "multi_island": ("2", "true"),
    }.get(condition)
    if topology is None:
        errors.append("unknown topology")
    else:
        expected_overrides = {
            "islands.count": topology[0],
            "islands.migration.enabled": topology[1],
            "agents.count": "8",
            "agents.runtime": "opencode",
            "agents.model": "mafia/glm-5.2",
            "agents.timeout": "300",
            "agents.sandbox.network": "allowlist",
            "agents.sandbox.allowed_domains": '["api.appintheloop.com"]',
            "grader.parallel.max_workers": "4",
            "grader.args.disable_tune": "true",
            "grader.args.mode": mode,
            "grader.args.seed_index": str(int(identity["repetition"]) - 1),
            "run.stop.max_real_attempts": str(budget),
            "run.stop.max_real_attempts_per_agent": str(budget // 8),
            "agents.runtime_options.role_file": str(ROLE_FILE),
            "agents.heartbeat": heartbeat_for(mode),
            "islands.migration.every": str(MIGRATION_EVERY[mode]),
            "islands.migration.rank_window": str(MIGRATION_EVERY[mode]),
            "islands.migration.remigration_cooldown": str(MIGRATION_EVERY[mode]),
        }
        for key, expected in expected_overrides.items():
            if values.get(key) != expected:
                errors.append(f"{key}={values.get(key)!r}, expected {expected!r}")

    if budget not in BUDGETS[mode]:
        errors.append(f"unregistered {mode} budget")
    resolved_path = run_dir / ".coral/config.yaml"
    try:
        resolved = yaml.safe_load(resolved_path.read_text())
        allowed_domains = resolved["agents"]["sandbox"].get("allowed_domains", [])
    except (OSError, TypeError, KeyError, yaml.YAMLError):
        errors.append("resolved config is unreadable")
    else:
        if allowed_domains != list(MODEL_API_DOMAINS):
            errors.append(
                f"network allowlist={allowed_domains!r}, expected model API only"
            )
    private = run_dir / ".coral/private" / SEED_BUNDLE_FILENAME
    if not private.is_file() or private.read_bytes() != TASKDATA.read_bytes():
        errors.append("private v8 seed bundle mismatch")
    records = common.real_records(run_dir)
    if len(records) != budget:
        errors.append(f"real attempts={len(records)}, expected {budget}")
    if any(
        record.get("metadata", {}).get("budget_class") in {"grader_error", "tune"}
        for record in common.all_records(run_dir)
    ):
        errors.append("disallowed tune/grader-error attempt present")
    stop = common.load_json(run_dir / ".coral/public/auto_stop.json") or {}
    if stop.get("reason") != "max_real_attempts":
        errors.append(f"auto-stop reason={stop.get('reason')!r}")
    migrations = list(run_dir.glob(".coral/islands/*/notes/migrations/migration_*.md"))
    if condition != "multi_island" and migrations:
        errors.append("migration notes in control")
    if condition == "multi_island" and budget >= MIGRATION_EVERY[mode] and not migrations:
        errors.append("multi-island cell has no migration event")
    if condition != "multi_island" and row["transferred_blocks"]:
        errors.append("cross-island certificate reuse in a non-migration control")
    isolated, isolation_violations = isolation_gate(run_dir)
    row["isolation_trace_gate"] = isolated
    row["isolation_trace_violation_count"] = len(isolation_violations)
    row["isolation_trace_violations"] = ";".join(isolation_violations)
    if not isolated:
        errors.append("cross-island information access in runtime trace")
    if row["numeric_scores"] != row["real_attempts"]:
        errors.append("non-numeric real score present")
    if row["parse_error_count"] > MAX_MALFORMED_ATTEMPTS:
        errors.append(
            f"candidate parse errors={row['parse_error_count']}, allowed {MAX_MALFORMED_ATTEMPTS}"
        )
    if row["feedback_error_count"]:
        errors.append(f"feedback integrity errors={row['feedback_error_count']}")
    if row["search_protocol_error_count"]:
        errors.append(
            f"registered search-operator errors={row['search_protocol_error_count']}"
        )
    if row["real_attempts"] == budget and not row["coverage_gate"]:
        errors.append(f"module coverage={row['module_coverage']}, below v8 gate")
    first_frontier = MODULE_COST[mode] * 8
    if budget >= first_frontier and row["global_discovered_blocks"] < 1:
        errors.append("no exact certificate above calibrated first-certificate frontier")
    if row["real_attempts"] == budget and not row["agent_quota_gate"]:
        errors.append(
            "per-agent quota failed: "
            f"min={row['agent_attempt_min']}, max={row['agent_attempt_max']}"
        )
    return errors


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def bootstrap_interval(values: list[float], *, samples: int = 20_000) -> tuple[float, float]:
    if not values:
        return float("nan"), float("nan")
    rng = random.Random(8_032_032 + len(values))
    means = sorted(
        statistics.fmean(rng.choice(values) for _ in values)
        for _ in range(samples)
    )
    return means[int(0.025 * samples)], means[min(samples - 1, int(0.975 * samples))]


def contrasts(rows: list[dict[str, Any]], repetitions: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    indexed = {
        (row["task"], row["budget"], row["condition"], row["repetition"]): row
        for row in rows
    }
    output: list[dict[str, Any]] = []
    thresholds: dict[str, Any] = {}
    for task in TASKS:
        mode = mode_for(task)
        first_passing: int | None = None
        for budget in BUDGETS[mode]:
            pairs = []
            transfer_compliance = []
            for repetition in range(1, repetitions + 1):
                left = indexed.get((task, budget, "multi_island", repetition))
                right = indexed.get((task, budget, "partition", repetition))
                if left is None or right is None:
                    continue
                pairs.append(
                    float(left["best_submitted_certified_blocks"])
                    - float(right["best_submitted_certified_blocks"])
                )
                transfer_compliance.append(left["transferred_blocks"] >= 1)
            if not pairs:
                continue
            low, high = bootstrap_interval(pairs)
            confirmatory_ready = len(pairs) == 8 and repetitions == 8
            passes = (
                confirmatory_ready
                and statistics.fmean(pairs) >= 2.0
                and low > 0.0
                and all(transfer_compliance)
            )
            if passes and first_passing is None:
                first_passing = budget
            output.append(
                {
                    "task": task,
                    "budget": budget,
                    "contrast": "multi_island_minus_partition",
                    "paired_repetitions": len(pairs),
                    "mean_difference_blocks": statistics.fmean(pairs),
                    "median_difference_blocks": statistics.median(pairs),
                    "bootstrap_low": low,
                    "bootstrap_high": high,
                    "all_multi_cells_reused_foreign_certificate": all(transfer_compliance),
                    "confirmatory_ready": confirmatory_ready,
                    "threshold_rule_passes": passes,
                }
            )
        thresholds[task] = {
            "registered_repetitions": 8,
            "practical_effect_blocks": 2,
            "earliest_passing_budget": first_passing,
        }
    return output, thresholds


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-root",
        type=Path,
        default=Path("/var/tmp/coral-institutions-results/modular-hard-v8"),
    )
    parser.add_argument("--tasks", nargs="+", choices=TASKS, default=list(TASKS))
    parser.add_argument("--conditions", nargs="+", choices=CONDITIONS, default=list(CONDITIONS))
    parser.add_argument("--budgets", nargs="+", type=int)
    parser.add_argument("--repetitions", type=int, default=8)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "analysis_hard_v8")
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    accepted: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    expected = 0
    for task in args.tasks:
        mode = mode_for(task)
        budgets = list(BUDGETS[mode]) if args.budgets is None else args.budgets
        invalid = [budget for budget in budgets if budget not in BUDGETS[mode]]
        if invalid:
            raise SystemExit(f"unregistered {mode} budgets: {invalid}")
        for budget in budgets:
            for condition in args.conditions:
                for repetition in range(1, args.repetitions + 1):
                    expected += 1
                    run_dir = (
                        args.results_root.resolve()
                        / f"budget-{budget}"
                        / task
                        / condition
                        / f"rep-{repetition:02d}"
                    )
                    identity = common.load_json(run_dir / "operator-command.json")
                    if identity is None:
                        failures.append(
                            {
                                "task": task,
                                "budget": budget,
                                "condition": condition,
                                "repetition": repetition,
                                "reasons": ["missing run"],
                            }
                        )
                        continue
                    row = collect(run_dir, identity, task, budget)
                    reasons = integrity(run_dir, identity, task, budget, row)
                    if reasons:
                        failures.append(
                            {
                                "task": task,
                                "budget": budget,
                                "condition": condition,
                                "repetition": repetition,
                                "run_dir": str(run_dir),
                                "reasons": reasons,
                                "observed": row,
                            }
                        )
                    else:
                        accepted.append(row)

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "runs.csv", accepted)
    contrast_rows, threshold_rows = contrasts(accepted, args.repetitions)
    write_csv(output / "contrasts.csv", contrast_rows)
    (output / "thresholds.json").write_text(json.dumps(threshold_rows, indent=2) + "\n")
    audit = {
        "schema_version": 1,
        "primary_metric": "best certificate-backed artifact actually submitted",
        "accepted_rows": len(accepted),
        "expected_rows": expected,
        "integrity_failures": failures,
    }
    (output / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(f"Audited {len(accepted)}/{expected} complete v8 cells; failures={len(failures)}")
    if failures and not args.allow_incomplete:
        raise SystemExit(f"v8 matrix incomplete; see {output / 'audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
