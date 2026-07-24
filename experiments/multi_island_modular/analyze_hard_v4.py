#!/usr/bin/env python3
"""Audit the v4 hard modular matrix with provenance and coverage gates."""

from __future__ import annotations

import argparse
import ast
import csv
import json
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
TASKDATA = ROOT / "tasks/hard_active_modular_landscape_v4/taskdata/hard_v4_seed_bundle.json"
SEED_BUNDLE_FILENAME = "hard_v4_seed_bundle.json"
SEED_SCHEMA_VERSION = 2
ROLE_PROTOCOL_FILENAME = "hard_v4_eval_protocol.md"
MIN_MODULE_COVERAGE = 8
MIN_ISLAND_COVERAGE = 4
MIGRATION_DIVISOR = 8
MIGRATION_MIN = 16
MIGRATION_MAX = 64
REMIGRATION_COOLDOWN = 16
ANALYZER_LABEL = "Hard v4"
PRIMARY_METRIC = "provenance-backed assembly"
MIN_EXACT_SIGNAL = 0
TOPOLOGY_AGENT_COUNTS = {
    "global": "4",
    "global_8": "8",
    "partition": "4",
    "multi_island": "4",
}
TASKS = ("smooth_hard_v4", "rugged_hard_v4")
CONDITIONS = ("global", "global_8", "partition", "multi_island")
REPETITIONS = 8
GRADER_SRC = ROOT / "tasks/hard_active_modular_landscape_v4/grader/src"
sys.path.insert(0, str(GRADER_SRC))
from hard_active_modular_landscape_grader.grader import (  # noqa: E402
    BLOCKS,
    CODEBOOK_SIZE,
    TOTAL_WIDTH,
    WIDTH,
    active_score,
    rugged_target,
    target_bits,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", nargs="+", choices=TASKS, default=list(TASKS))
    parser.add_argument("--conditions", nargs="+", choices=CONDITIONS, default=list(CONDITIONS))
    parser.add_argument("--repetitions", type=int, default=REPETITIONS)
    parser.add_argument(
        "--results-root", type=Path, default=Path("/var/tmp/coral-institutions-results/modular-hard-v4")
    )
    parser.add_argument("--budgets", type=int, nargs="+", default=[384, 768, 1536, 3072, 6144, 8192])
    parser.add_argument("--output-dir", type=Path, default=ROOT / "hard-v4-analysis")
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
    if (
        value is None
        or value.get("schema_version") != SEED_SCHEMA_VERSION
        or value.get("blocks") != BLOCKS
        or value.get("block_width") != WIDTH
        or value.get("codebook_size") != CODEBOOK_SIZE
    ):
        raise ValueError("invalid frozen v4 seed bundle")
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
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and type(node.value.value) is str:
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name, value = node.target.id, node.value
        else:
            raise ValueError("candidate may only contain a docstring and two assignments")
        if name == "CANDIDATE":
            if candidate is not None:
                raise ValueError("duplicate CANDIDATE")
            if isinstance(value, ast.Constant) and type(value.value) is str:
                candidate = value.value
            elif isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == BLOCKS:
                modules = []
                for item in value.elts:
                    if not isinstance(item, ast.Constant) or type(item.value) is not str:
                        raise ValueError("CANDIDATE modules must be literal strings")
                    modules.append(item.value)
                if any(len(module) != WIDTH or set(module) - {"0", "1"} for module in modules):
                    raise ValueError("invalid v4 module literal")
                candidate = "".join(modules)
            else:
                raise ValueError("CANDIDATE must be a string or tuple/list literal")
        elif name == "ACTIVE_MODULE":
            if active is not None or not isinstance(value, ast.Constant) or type(value.value) is not int:
                raise ValueError("ACTIVE_MODULE must be one integer literal")
            active = value.value
        else:
            raise ValueError("invalid candidate assignment")
    if candidate is None or active is None or len(candidate) != TOTAL_WIDTH or set(candidate) - {"0", "1"}:
        raise ValueError("invalid hard v4 artifact")
    if not 0 <= active < BLOCKS:
        raise ValueError("ACTIVE_MODULE outside v4 module range")
    return candidate, active


def targets(task: str, seed: str) -> list[str]:
    fn = target_bits if mode_for(task) == "smooth" else rugged_target
    return [fn(seed, block, WIDTH) for block in range(BLOCKS)]


def assembled_score(candidate: str, task: str, seed: str, known: dict[int, str]) -> tuple[float, int]:
    mode = mode_for(task)
    target_list = targets(task, seed)
    scores = []
    exact = 0
    for block in range(BLOCKS):
        bits = candidate[block * WIDTH : (block + 1) * WIDTH]
        backed = known.get(block) == bits
        exact += int(backed)
        scores.append(1.0 if backed else active_score("0" * WIDTH, mode=mode, target=target_list[block]))
    return statistics.fmean(scores), exact


def all_records(run_dir: Path) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for path in run_dir.glob(".coral/**/attempts/*.json"):
        record = load_json(path)
        if record is None or record.get("status") == "pending":
            continue
        commit = record.get("commit_hash")
        if isinstance(commit, str):
            record["_attempt_path"] = str(path)
            records[commit] = record
    return sorted(records.values(), key=lambda item: (str(item.get("timestamp", "")), str(item.get("commit_hash", ""))))


def real_records(run_dir: Path) -> list[dict[str, Any]]:
    return [
        record
        for record in all_records(run_dir)
        if record.get("metadata", {}).get("budget_class", "real") == "real"
    ]


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


def record_island(record: dict[str, Any]) -> str:
    """Recover the island scope from the attempt path when available."""
    path = Path(str(record.get("_attempt_path", "")))
    parts = path.parts
    try:
        index = parts.index("islands")
    except ValueError:
        return "global"
    return parts[index + 1] if index + 1 < len(parts) else "unknown"


def overrides(identity: dict[str, Any]) -> dict[str, str]:
    return {
        item.split("=", 1)[0]: item.split("=", 1)[1]
        for item in identity.get("command", [])
        if isinstance(item, str) and "=" in item
    }


def integrity(run_dir: Path, identity: dict[str, Any], task: str, budget: int) -> list[str]:
    errors: list[str] = []
    values = overrides(identity)
    condition = str(identity.get("condition"))
    agent_count = TOPOLOGY_AGENT_COUNTS.get(condition)
    topology = {
        "global": ("1", "false"),
        "global_8": ("1", "false"),
        "partition": ("2", "false"),
        "multi_island": ("2", "true"),
    }.get(condition)
    if topology is None:
        errors.append("unknown topology")
    else:
        for key, expected in (
            ("islands.count", topology[0]),
            ("islands.migration.enabled", topology[1]),
            ("agents.count", agent_count),
        ):
            if values.get(key) != expected:
                errors.append(f"{key}={values.get(key)!r}, expected {expected!r}")
    every = max(MIGRATION_MIN, min(MIGRATION_MAX, budget // MIGRATION_DIVISOR))
    expected = {
        "agents.runtime": "opencode",
        "agents.model": "mafia/glm-5.2",
        "grader.parallel.max_workers": "4",
        "grader.args.disable_tune": "true",
        "grader.args.mode": mode_for(task),
        "run.stop.max_real_attempts": str(budget),
        "grader.args.seed_index": str(int(identity.get("repetition", 1)) - 1),
        "islands.migration.every": str(every),
        "islands.migration.rank_window": str(every),
        "islands.migration.remigration_cooldown": str(REMIGRATION_COOLDOWN),
    }
    for key, expected_value in expected.items():
        if values.get(key) != expected_value:
            errors.append(f"{key}={values.get(key)!r}, expected {expected_value!r}")
    if values.get("agents.runtime_options.role_file") != str(ROOT / ROLE_PROTOCOL_FILENAME):
        errors.append("wrong v4 role protocol")
    private = run_dir / ".coral/private" / SEED_BUNDLE_FILENAME
    if not private.is_file() or private.read_bytes() != TASKDATA.read_bytes():
        errors.append("private v4 seed bundle mismatch")
    records = real_records(run_dir)
    if len(records) != budget:
        errors.append(f"real attempts={len(records)}, expected {budget}")
    if any(record.get("metadata", {}).get("budget_class") in {"grader_error", "tune"} for record in all_records(run_dir)):
        errors.append("disallowed tune/grader-error attempt present")
    stop = load_json(run_dir / ".coral/public/auto_stop.json") or {}
    if stop.get("reason") != "max_real_attempts":
        errors.append(f"auto-stop reason={stop.get('reason')!r}")
    migrations = list(run_dir.glob(".coral/islands/*/notes/migrations/migration_*.md"))
    if condition != "multi_island" and migrations:
        errors.append("migration notes in control")
    if condition == "multi_island" and budget >= every and not migrations:
        errors.append("multi-island cell has no migration event")
    return errors


def collect(run_dir: Path, identity: dict[str, Any], task: str, budget: int) -> dict[str, Any]:
    seed = str(bundle()["seeds"][int(identity["repetition"]) - 1])
    # Keep the provenance ledger in temporal order.  It is tempting to build
    # ``known`` from every exact result first and then score every candidate
    # against that final ledger, but that gives an early candidate credit for
    # a module that nobody had tested yet.  Such retrospective credit is
    # especially damaging to the migration contrast: it can turn lucky bits
    # into apparent transferred knowledge.  A candidate may use exact bits
    # known before its submission and the module tested by its own submission;
    # future exact discoveries must not affect it.
    parsed: list[tuple[dict[str, Any], str, int, float, int]] = []
    known: dict[int, str] = {}
    parse_errors: list[str] = []
    island_modules: defaultdict[str, set[int]] = defaultdict(set)
    records = real_records(run_dir)
    for record in records:
        try:
            candidate, active = parse_artifact(source_at(run_dir, str(record["commit_hash"])))
            island_modules[record_island(record)].add(active)
            if record.get("score") == 1.0:
                known[active] = candidate[active * WIDTH : (active + 1) * WIDTH]
            score, exact = assembled_score(candidate, task, seed, known)
            parsed.append((record, candidate, active, score, exact))
        except (OSError, ValueError, SyntaxError, KeyError, TypeError):
            parse_errors.append(str(record.get("commit_hash")))
    best = (0.0, 0, "")
    for _, candidate, _, score, exact in parsed:
        if (score, exact) > (best[0], best[1]):
            best = (score, exact, candidate)
    baseline, _ = assembled_score("0" * TOTAL_WIDTH, task, seed, {})
    pooled_candidate = list("0" * TOTAL_WIDTH)
    for block, bits in known.items():
        pooled_candidate[block * WIDTH : (block + 1) * WIDTH] = bits
    pooled_score, pooled_exact = assembled_score("".join(pooled_candidate), task, seed, known)
    coverage = len({active for _, _, active, _, _ in parsed})
    island_coverage = {island: len(modules) for island, modules in island_modules.items()}
    multi_island_gate = str(identity["condition"]) != "multi_island" or (
        len(island_coverage) >= 2 and min(island_coverage.values()) >= MIN_ISLAND_COVERAGE
    )
    return {
        "task": task,
        "condition": str(identity["condition"]),
        "repetition": int(identity["repetition"]),
        "budget": budget,
        "real_attempts": len(records),
        "numeric_scores": sum(isinstance(record.get("score"), (int, float)) for record in records),
        "score_range": (
            max(float(record["score"]) for record in records if isinstance(record.get("score"), (int, float)))
            - min(float(record["score"]) for record in records if isinstance(record.get("score"), (int, float)))
            if any(isinstance(record.get("score"), (int, float)) for record in records)
            else 0.0
        ),
        "best_assembled_score": best[0] if parsed else baseline,
        "best_tested_blocks": best[1] if parsed else 0,
        "final_known_blocks": len(known),
        "pooled_assembled_score": pooled_score,
        "pooled_tested_blocks": pooled_exact,
        "assembly_gap": pooled_score - (best[0] if parsed else baseline),
        "module_coverage": coverage,
        "island_coverage": json.dumps(island_coverage, sort_keys=True),
        "coverage_gate": coverage >= min(MIN_MODULE_COVERAGE, BLOCKS) and multi_island_gate,
        "parse_errors": ";".join(parse_errors),
    }


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
        for task in args.tasks:
            for condition in args.conditions:
                for repetition in range(1, args.repetitions + 1):
                    run_dir = root / f"budget-{budget}" / task / condition / f"rep-{repetition:02d}"
                    identity = load_json(run_dir / "operator-command.json")
                    if identity is None:
                        failures.append({"budget": budget, "task": task, "condition": condition, "repetition": repetition, "reasons": ["missing run"]})
                        continue
                    reasons = integrity(run_dir, identity, task, budget)
                    row = collect(run_dir, identity, task, budget)
                    if row["parse_errors"]:
                        reasons.append(f"candidate parse errors: {row['parse_errors']}")
                    if row["numeric_scores"] != row["real_attempts"]:
                        reasons.append("non-numeric real score present")
                    if row["real_attempts"] == budget and row["score_range"] <= 1e-12:
                        reasons.append("degenerate score range")
                    if row["real_attempts"] == budget and not row["coverage_gate"]:
                        reasons.append(
                            f"module coverage={row['module_coverage']}, need at least {MIN_MODULE_COVERAGE}"
                        )
                    if row["real_attempts"] == budget and row["final_known_blocks"] < MIN_EXACT_SIGNAL:
                        reasons.append(
                            f"exact signal={row['final_known_blocks']}, need at least {MIN_EXACT_SIGNAL}"
                        )
                    if reasons:
                        failures.append(
                            {
                                "budget": budget,
                                "task": task,
                                "condition": condition,
                                "repetition": repetition,
                                "run_dir": str(run_dir),
                                "reasons": reasons,
                                "observed": row,
                            }
                        )
                    else:
                        rows.append(row)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "runs.csv", rows)
    audit = {
        "schema_version": 2,
        "tasks": args.tasks,
        "conditions": args.conditions,
        "budgets": args.budgets,
        "repetitions": args.repetitions,
        "complete_rows": len(rows),
        "expected_rows": len(args.tasks) * len(args.conditions) * args.repetitions * len(args.budgets),
        "integrity_failures": failures,
        "primary_metric": PRIMARY_METRIC,
        "coverage_gate": (
            f"at least {MIN_MODULE_COVERAGE} distinct active modules; multi-island "
            f"also needs at least {MIN_ISLAND_COVERAGE} per island"
        ),
        "exact_signal_gate": f"at least {MIN_EXACT_SIGNAL} provenance-backed exact modules",
    }
    (output / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(f"Audited {len(rows)} complete cells; failures={len(failures)}")
    if failures and not args.allow_incomplete:
        raise SystemExit(f"{ANALYZER_LABEL} matrix incomplete; see {output / 'audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
