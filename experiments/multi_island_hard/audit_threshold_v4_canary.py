#!/usr/bin/env python3
"""Fail-closed audit for the scripted threshold-v4 topology canary.

This audit establishes treatment fidelity only.  It deliberately computes no
topology effect and must not be cited as performance or institutions evidence.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import random
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from experiments.multi_island.isolation_audit import isolation_gate
from experiments.multi_island_hard import analyze_threshold_v2 as base
from experiments.multi_island_hard import run_threshold_v4_canary as canary

ATTEMPTS_PER_AGENT = canary.CANARY_BUDGET // 8


def base_agent_id(agent_id: str) -> str:
    return agent_id.strip().split("-from-", 1)[0]


def expected_initial(agent_id: str, n: int = 512) -> str:
    digest = hashlib.sha256(
        f"coral-threshold-v4:{base_agent_id(agent_id)}".encode()
    ).digest()
    bits = "".join(f"{byte:08b}" for byte in digest)
    while len(bits) < n:
        digest = hashlib.sha256(digest).digest()
        bits += "".join(f"{byte:08b}" for byte in digest)
    return bits[:n]


def expected_mutation_indices(
    agent_id: str,
    local_attempt: int,
    n: int = 512,
) -> tuple[int, ...]:
    """Recompute the frozen controller schedule independently of its trace."""

    if local_attempt < 2:
        raise ValueError("a mutation local_attempt must be at least 2")
    schedule_index = local_attempt - 1
    label = (
        f"threshold-v4-scripted-policy:{base_agent_id(agent_id)}:{schedule_index}"
    )
    seed = int.from_bytes(hashlib.sha256(label.encode()).digest()[:8], "big")
    rng = random.Random(seed)
    draw = rng.random()
    count = 1 if draw < 0.90 else 2 if draw < 0.98 else 4
    return tuple(sorted(rng.sample(range(n), count)))


def literal_candidate(source: str) -> str:
    tree = ast.parse(source)
    values = [
        node.value.value
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    if len(values) != 1 or len(values[0]) != 512 or set(values[0]) - {"0", "1"}:
        raise ValueError("candidate.py does not contain one 512-bit literal")
    return values[0]


def source_candidate(run_dir: Path, commit: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(run_dir / "repo"), "show", f"{commit}:candidate.py"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"cannot read candidate at {commit}: {result.stderr.strip()}")
    return literal_candidate(result.stdout)


def source_candidates(run_dir: Path, commits: set[str]) -> dict[str, str]:
    """Read candidate blobs through one persistent Git batch process."""
    process = subprocess.Popen(
        ["git", "-C", str(run_dir / "repo"), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdin is None or process.stdout is None:
        process.kill()
        raise ValueError("cannot open git cat-file batch pipes")
    candidates: dict[str, str] = {}
    try:
        for commit in sorted(commits):
            process.stdin.write(f"{commit}:candidate.py\n".encode())
            process.stdin.flush()
            header = process.stdout.readline().decode(errors="replace").strip()
            parts = header.rsplit(" ", 2)
            if len(parts) != 3 or parts[1] != "blob":
                raise ValueError(f"cannot read candidate at {commit}: {header}")
            try:
                size = int(parts[2])
            except ValueError as exc:
                raise ValueError(f"invalid candidate blob size at {commit}") from exc
            source = process.stdout.read(size).decode(errors="strict")
            if process.stdout.read(1) != b"\n":
                raise ValueError(f"invalid git batch delimiter at {commit}")
            candidates[commit] = literal_candidate(source)
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    if process.returncode != 0:
        stderr = process.stderr.read().decode(errors="replace") if process.stderr else ""
        raise ValueError(f"git cat-file batch failed: {stderr.strip()}")
    return candidates


def load_traces(
    run_dir: Path,
    *,
    attempts_per_agent: int = ATTEMPTS_PER_AGENT,
) -> tuple[list[dict[str, Any]], list[str]]:
    traces: list[dict[str, Any]] = []
    errors: list[str] = []
    for worktree in sorted((run_dir / "agents").iterdir()):
        breadcrumb = worktree / ".coral_island"
        expected_attempts = run_dir / ".coral/public/attempts"
        if breadcrumb.is_file():
            expected_attempts = (
                run_dir / ".coral/islands" / breadcrumb.read_text().strip() / "attempts"
            )
        actual_attempts = worktree / ".scripted/attempts"
        if not actual_attempts.is_symlink() or actual_attempts.resolve() != expected_attempts.resolve():
            errors.append(f"{worktree.name}: shared attempts symlink disagrees with breadcrumb")
        path = worktree / ".coral-tmp" / "scripted-policy.jsonl"
        if not path.is_file():
            errors.append(f"{worktree.name}: missing scripted trace")
            continue
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{worktree.name}:{line_number}: invalid trace JSON: {exc}")
                continue
            if not isinstance(record, dict):
                errors.append(f"{worktree.name}:{line_number}: trace is not an object")
                continue
            if record.get("agent_id") != worktree.name:
                errors.append(f"{worktree.name}:{line_number}: agent identity mismatch")
            traces.append(record)
        state_path = worktree / ".coral-tmp" / "scripted-policy-state.json"
        state = base.load_json(state_path)
        if state is None:
            errors.append(f"{worktree.name}: missing durable policy state")
        elif state.get("completed_attempts") != attempts_per_agent or state.get(
            "pending"
        ) is not None:
            errors.append(f"{worktree.name}: incomplete durable policy state")
    return traces, errors


def sequence_errors(
    traces: list[dict[str, Any]],
    *,
    expected_agents: int = 8,
    attempts_per_agent: int = ATTEMPTS_PER_AGENT,
) -> list[str]:
    errors: list[str] = []
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for trace in traces:
        grouped[base_agent_id(str(trace.get("agent_id", "")))].append(trace)
    if len(grouped) != expected_agents:
        errors.append(f"base agents={len(grouped)}, expected {expected_agents}")
    for agent, rows in sorted(grouped.items()):
        raw_attempts = [row.get("local_attempt") for row in rows]
        if not all(isinstance(value, int) for value in raw_attempts):
            errors.append(f"{agent}: missing or non-integer local attempt")
            continue
        attempts = sorted(int(value) for value in raw_attempts)
        expected = list(range(1, attempts_per_agent + 1))
        if attempts != expected:
            errors.append(f"{agent}: local attempts={attempts}, expected {expected}")
            continue
        by_attempt = {int(row["local_attempt"]): row for row in rows}
        if by_attempt[1].get("type") != "initial":
            errors.append(f"{agent}: local attempt 1 is not initial")
        for local_attempt in range(2, attempts_per_agent + 1):
            if by_attempt[local_attempt].get("type") != "proposal":
                errors.append(f"{agent}: local attempt {local_attempt} is not proposal")
    return errors


def prompt_events(run_dir: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    roots = [run_dir / ".coral/public/logs"]
    roots.extend(sorted(run_dir.glob(".coral/islands/*/logs")))
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.log")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            for line in path.read_text(errors="replace").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    isinstance(event, dict)
                    and event.get("type") == "coral"
                    and event.get("subtype") == "prompt"
                ):
                    event["log_island"] = (
                        path.parent.parent.name if "islands" in path.parts else None
                    )
                    events.append(event)
    return events


def _command_overrides(identity: dict[str, Any]) -> dict[str, str]:
    command = identity.get("command")
    if not isinstance(command, list):
        return {}
    values: dict[str, str] = {}
    for item in command:
        if isinstance(item, str) and "=" in item:
            key, value = item.split("=", 1)
            values[key] = value
    return values


def configuration_errors(
    run_dir: Path,
    condition: str,
    *,
    budget: int = canary.CANARY_BUDGET,
    attempts_per_agent: int = ATTEMPTS_PER_AGENT,
    migration_every: int = 8,
    grader_workers: int = 4,
    seed_index: int = 0,
) -> list[str]:
    errors: list[str] = []
    identity = base.load_json(run_dir / "operator-command.json")
    if identity is None:
        return ["missing operator identity"]
    values = _command_overrides(identity)
    topology = canary.runner.base.TOPOLOGIES[condition]
    expected = {
        "agents.count": "8",
        "agents.runtime": canary.SCRIPTED_RUNTIME,
        "agents.model": "scripted",
        "agents.timeout": "0",
        "agents.sandbox.network": "allowlist",
        "agents.sandbox.allowed_domains": "[]",
        "grader.parallel.max_workers": str(grader_workers),
        "grader.args.disable_tune": "true",
        "grader.args.seed_index": str(seed_index),
        "islands.count": str(topology["count"]),
        "islands.migration.enabled": str(topology["migration"]).lower(),
        "islands.migration.every": str(migration_every),
        "islands.migration.rank_window": str(migration_every),
        "islands.migration.max_per_cycle": str(topology["max_per_cycle"]),
        "islands.migration.remigration_cooldown": str(migration_every),
        "islands.migration.dest_weighting": "round_robin",
        "run.stop.max_real_attempts": str(budget),
        "run.stop.max_real_attempts_per_agent": str(attempts_per_agent),
    }
    for key, expected_value in expected.items():
        if values.get(key) != expected_value:
            errors.append(f"{key}={values.get(key)!r}, expected {expected_value!r}")
    runtime_command = values.get("agents.runtime_options.command", "")
    if "scripted_search.py" not in runtime_command or "--visible-agents" not in runtime_command:
        errors.append("scripted runtime command is missing its registered controller")
    return errors


def trace_semantic_errors(
    run_dir: Path,
    traces: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    attempts = {str(record.get("commit_hash")): record for record in records}
    trace_commits = [str(trace.get("commit_hash", "")) for trace in traces]
    if len(set(trace_commits)) != len(trace_commits):
        errors.append("trace commit hashes are not unique")
    if set(trace_commits) != set(attempts):
        missing = sorted(set(attempts) - set(trace_commits))
        extra = sorted(set(trace_commits) - set(attempts))
        errors.append(f"trace/attempt commit mismatch: missing={missing}, extra={extra}")
    try:
        candidate_cache = source_candidates(run_dir, set(attempts))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        errors.append(str(exc))
        return errors

    def candidate(commit: str) -> str:
        try:
            return candidate_cache[commit]
        except KeyError as exc:
            raise ValueError(f"candidate commit is not a real attempt: {commit}") from exc

    for trace in traces:
        commit = str(trace.get("commit_hash", ""))
        local_attempt = trace.get("local_attempt")
        agent = str(trace.get("agent_id", ""))
        record = attempts.get(commit)
        label = f"{base_agent_id(agent)}:{local_attempt}"
        if record is None:
            continue
        if base_agent_id(str(record.get("agent_id", ""))) != base_agent_id(agent):
            errors.append(f"{label}: attempt owner mismatch")
        if f"attempt={local_attempt}" not in str(record.get("title", "")):
            errors.append(f"{label}: attempt title lacks local sequence")
        try:
            child = candidate(commit)
        except (ValueError, SyntaxError) as exc:
            errors.append(f"{label}: {exc}")
            continue
        digest = hashlib.sha256(child.encode()).hexdigest()
        if trace.get("candidate_sha256") != digest:
            errors.append(f"{label}: candidate trace hash mismatch")
        recovery_submissions = trace.get("admission_recovery_submissions")
        if not isinstance(recovery_submissions, int) or recovery_submissions < 0:
            errors.append(f"{label}: invalid admission recovery count")
        if trace.get("type") == "initial":
            expected = expected_initial(agent)
            if child != expected:
                errors.append(f"{label}: committed initial candidate mismatch")
            continue
        if trace.get("type") != "proposal":
            errors.append(f"{label}: unknown trace type")
            continue
        parent_hash = str(trace.get("parent_hash", ""))
        parent_record = attempts.get(parent_hash)
        if parent_record is None:
            errors.append(f"{label}: parent is not a real attempt")
            continue
        try:
            parent = candidate(parent_hash)
        except (ValueError, SyntaxError) as exc:
            errors.append(f"{label}: invalid parent: {exc}")
            continue
        actual_flips = [
            index
            for index, (left, right) in enumerate(zip(parent, child, strict=True))
            if left != right
        ]
        if actual_flips != trace.get("flips"):
            errors.append(f"{label}: committed Hamming delta does not match trace")
        try:
            registered_flips = expected_mutation_indices(agent, int(local_attempt))
        except (TypeError, ValueError):
            errors.append(f"{label}: invalid mutation local sequence")
        else:
            if tuple(actual_flips) != registered_flips:
                errors.append(f"{label}: mutation differs from registered schedule")
        if trace.get("policy") != "registered_mixed":
            errors.append(f"{label}: unregistered scripted policy")
        if len(actual_flips) not in {1, 2, 4}:
            errors.append(f"{label}: unregistered mutation radius {len(actual_flips)}")
        visible_top = trace.get("visible_top")
        if not isinstance(visible_top, list) or not visible_top:
            errors.append(f"{label}: missing visible ranking")
            continue
        if visible_top[0].get("commit_hash") != parent_hash:
            errors.append(f"{label}: parent is not recorded visible champion")
        scores = [row.get("score") for row in visible_top]
        if not all(isinstance(score, (int, float)) for score in scores) or scores != sorted(
            scores, reverse=True
        ):
            errors.append(f"{label}: visible ranking is not score-descending")
        if trace.get("parent_score") != parent_record.get("score"):
            errors.append(f"{label}: parent score mismatch")
    return errors


def migration_errors(
    run_dir: Path,
    condition: str,
    traces: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    migrations = [event for event in events if event.get("source") == "migration"]
    heartbeat = [
        event for event in events if str(event.get("source", "")).startswith("heartbeat:")
    ]
    if heartbeat:
        errors.append(f"heartbeat interventions={len(heartbeat)}, expected 0")
    if condition != "multi_island_4":
        if migrations:
            errors.append(f"control contains {len(migrations)} migration restarts")
        if list(run_dir.glob(".coral/islands/*/notes/migrations/migration_*.md")):
            errors.append("control contains migration notes")
        return errors
    if not migrations:
        errors.append("multi-island treatment has no realized migration")
        return errors
    exposed_destinations: set[str] = set()
    migrated_destinations: set[str] = set()
    for event in migrations:
        destination = str(event.get("log_island", ""))
        if destination:
            migrated_destinations.add(destination)
        try:
            boundary = datetime.fromisoformat(str(event["timestamp"])).timestamp()
        except (KeyError, TypeError, ValueError):
            errors.append(
                f"{event.get('agent_id', '')}: migration event has invalid timestamp"
            )
            continue
        later = [
            trace
            for trace in traces
            if trace.get("type") == "proposal"
            and trace.get("island_id") == destination
            and isinstance(trace.get("selected_at"), (int, float))
            and float(trace["selected_at"]) > boundary
        ]
        if later:
            exposed_destinations.add(destination)
    # A budget-boundary migration can legitimately be the final event, after
    # every agent has exhausted its quota.  It has no causal exposure and is
    # not evidence by itself.  Require instead that every island destination
    # had at least one earlier migration followed by a policy proposal under
    # the destination's new visibility set.
    unexposed = sorted(migrated_destinations - exposed_destinations)
    if unexposed:
        errors.append(f"no post-migration proposal exposure in destinations={unexposed}")
    isolated, violations = isolation_gate(run_dir)
    if not isolated:
        errors.extend(f"isolation: {violation}" for violation in violations)
    return errors


def audit_run(
    run_dir: Path,
    condition: str,
    *,
    budget: int = canary.CANARY_BUDGET,
    attempts_per_agent: int = ATTEMPTS_PER_AGENT,
    migration_every: int = 8,
    grader_workers: int = 4,
    seed_index: int = 0,
) -> dict[str, Any]:
    errors = configuration_errors(
        run_dir,
        condition,
        budget=budget,
        attempts_per_agent=attempts_per_agent,
        migration_every=migration_every,
        grader_workers=grader_workers,
        seed_index=seed_index,
    )
    records = base.real_records(run_dir)
    if len(records) != budget:
        errors.append(f"real attempts={len(records)}, expected {budget}")
    if any(not isinstance(record.get("score"), (int, float)) for record in records):
        errors.append("non-numeric real score present")
    if base.disallowed_records(run_dir):
        errors.append("disallowed tune or grader-error attempt present")
    counts = Counter(base_agent_id(str(record.get("agent_id", ""))) for record in records)
    if len(counts) != 8 or set(counts.values()) != {attempts_per_agent}:
        errors.append(f"unbalanced base-agent quotas: {dict(sorted(counts.items()))}")
    stop = base.load_json(run_dir / ".coral/public/auto_stop.json") or {}
    if stop.get("reason") != "max_real_attempts":
        errors.append(f"auto-stop reason={stop.get('reason')!r}")
    traces, trace_load_errors = load_traces(
        run_dir,
        attempts_per_agent=attempts_per_agent,
    )
    errors.extend(trace_load_errors)
    errors.extend(sequence_errors(traces, attempts_per_agent=attempts_per_agent))
    type_counts = Counter(str(trace.get("type")) for trace in traces)
    expected_types = {"initial": 8, "proposal": budget - 8}
    if type_counts != expected_types:
        errors.append(
            f"trace types={dict(type_counts)}, expected 8 initial/{budget - 8} proposal"
        )
    errors.extend(trace_semantic_errors(run_dir, traces, records))
    events = prompt_events(run_dir)
    errors.extend(migration_errors(run_dir, condition, traces, events))
    return {
        "run_dir": str(run_dir),
        "condition": condition,
        "valid": not errors,
        "errors": errors,
        "real_attempts": len(records),
        "trace_types": dict(sorted(type_counts.items())),
        "base_agent_attempts": dict(sorted(counts.items())),
        "migration_events": sum(event.get("source") == "migration" for event in events),
        "heartbeat_events": sum(
            str(event.get("source", "")).startswith("heartbeat:") for event in events
        ),
        "traces": traces,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=canary.RESULTS_ROOT)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.results_root.resolve()
    budget_root = root if root.name == "budget-32" else root / "budget-32"
    cells: list[dict[str, Any]] = []
    schedules: defaultdict[tuple[str, int], set[tuple[int, ...]]] = defaultdict(set)
    initial_hashes: defaultdict[str, set[str]] = defaultdict(set)
    for task in canary.CANARY_TASKS:
        for condition in canary.CANARY_CONDITIONS:
            base_run_dir = budget_root / task / condition / "rep-01"
            candidates = base.existing_run_dirs(base_run_dir)
            if not candidates:
                cells.append(
                    {
                        "run_dir": str(base_run_dir),
                        "condition": condition,
                        "task": task,
                        "valid": False,
                        "errors": ["missing run"],
                    }
                )
                continue
            accepted: dict[str, Any] | None = None
            rejected: list[dict[str, Any]] = []
            for run_dir in candidates:
                cell = audit_run(run_dir, condition)
                cell["task"] = task
                if cell["valid"]:
                    accepted = cell
                    break
                rejected.append(cell)
            cell = accepted or rejected[-1]
            cell["superseded_invalid_runs"] = [
                row["run_dir"] for row in (rejected if accepted else rejected[:-1])
            ]
            if cell["valid"]:
                for trace in cell["traces"]:
                    agent = base_agent_id(str(trace["agent_id"]))
                    if trace["type"] == "initial":
                        initial_hashes[agent].add(str(trace["candidate_sha256"]))
                    else:
                        schedules[(agent, int(trace["local_attempt"]))].add(
                            tuple(int(index) for index in trace["flips"])
                        )
            cell.pop("traces", None)
            cells.append(cell)
    matrix_errors: list[str] = []
    for key, variants in sorted(schedules.items()):
        if len(variants) != 1:
            matrix_errors.append(f"mutation schedule differs across topology/task for {key}")
    for agent, variants in sorted(initial_hashes.items()):
        if len(variants) != 1:
            matrix_errors.append(f"initial candidate differs across topology/task for {agent}")
    valid_cells = sum(bool(cell.get("valid")) for cell in cells)
    audit = {
        "schema_version": 1,
        "scope": "scripted end-to-end topology mechanism canary; non-inferential",
        "valid_cells": valid_cells,
        "expected_cells": len(canary.CANARY_TASKS) * len(canary.CANARY_CONDITIONS),
        "matrix_errors": matrix_errors,
        "cells": cells,
        "interpretation": (
            "Passing proves controller/topology treatment fidelity only; it is not a "
            "multi-island performance result and not institutions evidence."
        ),
    }
    output = args.output or budget_root / "scripted-canary-audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(f"Audited {valid_cells}/{audit['expected_cells']} scripted canary cells")
    if valid_cells != audit["expected_cells"] or matrix_errors:
        raise SystemExit(f"scripted canary invalid; see {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
