#!/usr/bin/env python3
"""Audit the real-task scaling sweep and render the blog data/figure."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_ROOT = Path("/var/tmp/coral-institutions-results/real-scaling-v1")
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "analysis"
BLOG_DIR = REPO_ROOT / "blog"
TASK_DIRECTIONS = {"kernel": "minimize", "polyominoes": "maximize"}
TASK_LABELS = {"kernel": "Kernel Builder", "polyominoes": "Pack the Polyominoes"}
CONDITION_LABELS = {"global": "Global", "multi_island": "Multi-island"}
COLORS = {"global": "#667085", "multi_island": "#0F766E"}
AGENT_COUNTS = (1, 2, 4, 8, 16, 32)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--no-blog", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def real_attempts(run_dir: Path) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for path in run_dir.glob(".coral/**/attempts/*.json"):
        record = load_json(path)
        if record is None or record.get("status") == "pending":
            continue
        if record.get("metadata", {}).get("budget_class", "real") != "real":
            continue
        commit_hash = record.get("commit_hash")
        if isinstance(commit_hash, str):
            records[commit_hash] = record
    return sorted(
        records.values(),
        key=lambda record: (str(record.get("timestamp") or ""), record["commit_hash"]),
    )


def seconds_between(start: str | None, finish: str | None) -> float | None:
    if not start or not finish:
        return None
    try:
        return (datetime.fromisoformat(finish) - datetime.fromisoformat(start)).total_seconds()
    except ValueError:
        return None


def count_migrations(run_dir: Path) -> int:
    paths = set(run_dir.glob(".coral/islands/*/notes/migrations/*.md"))
    return len(paths)


def gateway_usage(run_dir: Path) -> dict[str, int]:
    """Sum recorded model usage without reading request or response content."""
    totals = {
        "model_requests": 0,
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    path = run_dir / ".coral/public/gateway/requests.jsonl"
    try:
        lines = path.open()
    except OSError:
        return totals
    with lines:
        for line in lines:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            response = record.get("response")
            if not isinstance(response, dict):
                continue
            usage = response.get("usage")
            if not isinstance(usage, dict):
                continue
            totals["model_requests"] += 1
            totals["input_tokens"] += int(usage.get("input_tokens") or 0)
            details = usage.get("input_tokens_details") or {}
            if not isinstance(details, dict):
                details = {}
            totals["cached_input_tokens"] += int(details.get("cached_tokens") or 0)
            totals["output_tokens"] += int(usage.get("output_tokens") or 0)
            totals["total_tokens"] += int(usage.get("total_tokens") or 0)
    return totals


def protocol_invalid(run_dir: Path) -> bool:
    """Return whether the operator explicitly quarantined this run.

    A quarantined run keeps its artifacts for auditability, but its scores must
    never enter the comparison.  The runner marks these cells by renaming the
    normal ``auto_stop.json`` sentinel to ``auto_stop.protocol-invalid.json``.
    """
    if any(run_dir.glob(".coral/public/auto_stop.protocol-invalid*.json")):
        return True
    # Keep the audit self-contained: a tune attempt is a protocol violation
    # even if an operator stopped the run before writing the quarantine
    # sentinel.
    for path in run_dir.glob(".coral/**/attempts/*.json"):
        record = load_json(path)
        if record and record.get("metadata", {}).get("budget_class") == "tune":
            return True
    return False


def audit_run(command_path: Path) -> dict[str, Any]:
    run_dir = command_path.parent
    identity = load_json(command_path)
    if identity is None:
        raise ValueError(f"unreadable operator record: {command_path}")
    result = load_json(run_dir / "operator-result.json") or {}
    attempts = real_attempts(run_dir)
    scores = [float(record["score"]) for record in attempts if record.get("score") is not None]
    task = str(identity["task"])
    direction = TASK_DIRECTIONS[task]
    best_score = None
    if scores:
        best_score = min(scores) if direction == "minimize" else max(scores)
    expected_raw = identity.get("expected_real_attempts")
    expected = int(expected_raw) if expected_raw is not None else None
    wall_clock_seconds = identity.get("wall_clock_seconds")
    auto_stop = load_json(run_dir / ".coral/public/auto_stop.json") or {}
    usage = gateway_usage(run_dir)
    if wall_clock_seconds is not None:
        complete = (
            result.get("status") == "complete"
            and not result.get("timed_out", False)
            and auto_stop.get("reason") == "wall_clock"
            and bool(scores)
        )
    else:
        complete = (
            result.get("status") == "complete"
            and auto_stop.get("reason") == "max_real_attempts"
            and expected is not None
            and len(attempts) == expected
            and bool(scores)
        )
    return {
        "task": task,
        "condition": str(identity["condition"]),
        "agent_count": int(identity["agent_count"]),
        "repetition": int(identity["repetition"]),
        "per_agent_budget": (
            int(identity["per_agent_budget"])
            if identity.get("per_agent_budget") is not None
            else None
        ),
        "total_budget": expected,
        "wall_clock_seconds": wall_clock_seconds,
        "real_attempts": len(attempts),
        "valid_scored_attempts": len(scores),
        "best_score": best_score,
        "wall_seconds": seconds_between(identity.get("started_at"), result.get("finished_at")),
        **usage,
        "migrations": count_migrations(run_dir),
        "protocol_valid": not protocol_invalid(run_dir),
        "complete": complete,
        "run_dir": str(run_dir),
        # Kept out of the published CSV.  It disambiguates a completed retry
        # from an older completed run of the same experimental cell.
        "_finished_at": result.get("finished_at"),
    }


def cell_identity(row: dict[str, Any]) -> tuple[str, str, int, int]:
    return (
        str(row["task"]),
        str(row["condition"]),
        int(row["agent_count"]),
        int(row["repetition"]),
    )


def expected_cell_identities(
    repetitions: set[int],
) -> set[tuple[str, str, int, int]]:
    return {
        (task, condition, agent_count, repetition)
        for task in TASK_DIRECTIONS
        for condition in CONDITION_LABELS
        for agent_count in AGENT_COUNTS
        for repetition in repetitions
        if not (condition == "multi_island" and agent_count == 1)
    }


def select_complete_cells(
    audited_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    """Select one valid completed run for each experimental cell.

    Failed attempts remain in the results tree for auditability.  A cell can
    also have more than one completed directory when an operator reruns it
    after repairing infrastructure.  In that case the latest completed run is
    the canonical observation, rather than counting the cell twice.
    """
    eligible = [
        row
        for row in audited_rows
        if row["protocol_valid"] and row["valid_scored_attempts"] > 0 and row["complete"]
    ]
    grouped: dict[tuple[str, str, int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        grouped[cell_identity(row)].append(row)

    selected = [
        max(
            rows,
            key=lambda row: (str(row.get("_finished_at") or ""), row["run_dir"]),
        )
        for rows in grouped.values()
    ]
    selected.sort(key=cell_identity)
    superseded = len(eligible) - len(selected)
    ineligible = len(audited_rows) - len(eligible)
    return selected, superseded, ineligible


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "task",
        "condition",
        "agent_count",
        "repetition",
        "per_agent_budget",
        "total_budget",
        "wall_clock_seconds",
        "real_attempts",
        "valid_scored_attempts",
        "best_score",
        "wall_seconds",
        "model_requests",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "total_tokens",
        "migrations",
        "protocol_valid",
        "complete",
        "run_dir",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row[field] for field in fields} for row in rows)


def mean_points(rows: list[dict[str, Any]]) -> dict[tuple[str, str, int], float]:
    grouped: dict[tuple[str, str, int], list[float]] = defaultdict(list)
    for row in rows:
        if row["complete"] and row["best_score"] is not None:
            grouped[(row["task"], row["condition"], row["agent_count"])].append(
                float(row["best_score"])
            )
    return {key: statistics.mean(values) for key, values in grouped.items()}


def chart_svg(rows: list[dict[str, Any]]) -> str:
    means = mean_points(rows)
    width, height = 1000, 390
    panel_width, panel_gap = 410, 90
    left, top, plot_height = 70, 58, 245
    counts = sorted({row["agent_count"] for row in rows if row["complete"]})
    if not counts:
        counts = [1, 2, 4, 8, 16, 32]
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'role="img" aria-label="Global and multi-island performance while scaling agents">',
        "<style>text{font-family:Inter,system-ui,sans-serif;fill:#475467}.title{font-size:18px;"
        "font-weight:700;fill:#101828}.label{font-size:12px}.tick{font-size:11px}.axis{stroke:#98A2B3;"
        "stroke-width:1}.grid{stroke:#EAECF0;stroke-width:1}.line{fill:none;stroke-width:2.5}.point{stroke-width:2;"
        "fill:white}.legend{font-size:12px;font-weight:600}</style>",
        '<rect width="100%" height="100%" fill="white"/>',
    ]

    for panel, task in enumerate(("kernel", "polyominoes")):
        x0 = left + panel * (panel_width + panel_gap)
        task_values = [
            score for (point_task, _condition, _count), score in means.items() if point_task == task
        ]
        if not task_values:
            task_values = [0.0, 1.0]
        low, high = min(task_values), max(task_values)
        pad = max((high - low) * 0.12, max(abs(low), abs(high), 1.0) * 0.02)
        low -= pad
        high += pad
        elements.append(
            f'<text class="title" x="{x0 + panel_width / 2}" y="28" text-anchor="middle">'
            f"{escape(TASK_LABELS[task])}</text>"
        )
        subtitle = "cycles (lower is better)" if task == "kernel" else "score (higher is better)"
        elements.append(
            f'<text class="label" x="{x0 + panel_width / 2}" y="47" text-anchor="middle">'
            f"{subtitle}</text>"
        )
        for tick_index in range(5):
            fraction = tick_index / 4
            y = top + fraction * plot_height
            # The top of both panels is always better.
            value = (
                low + fraction * (high - low)
                if task == "kernel"
                else high - fraction * (high - low)
            )
            elements.append(
                f'<line class="grid" x1="{x0}" y1="{y}" x2="{x0 + panel_width}" y2="{y}"/>'
            )
            elements.append(
                f'<text class="tick" x="{x0 - 10}" y="{y + 4}" text-anchor="end">{value:.2f}</text>'
            )
        elements.append(
            f'<line class="axis" x1="{x0}" y1="{top + plot_height}" '
            f'x2="{x0 + panel_width}" y2="{top + plot_height}"/>'
        )
        for index, count in enumerate(counts):
            x = x0 if len(counts) == 1 else x0 + index * panel_width / (len(counts) - 1)
            elements.append(
                f'<text class="tick" x="{x}" y="{top + plot_height + 21}" text-anchor="middle">{count}</text>'
            )
        elements.append(
            f'<text class="label" x="{x0 + panel_width / 2}" y="{top + plot_height + 46}" '
            'text-anchor="middle">agents</text>'
        )

        for condition in ("global", "multi_island"):
            points: list[tuple[float, float]] = []
            for index, count in enumerate(counts):
                key = (task, condition, count)
                # The one-agent global cell is the common topology-free origin.
                if key not in means and count == 1:
                    key = (task, "global", 1)
                if key not in means:
                    continue
                score = means[key]
                x = x0 if len(counts) == 1 else x0 + index * panel_width / (len(counts) - 1)
                fraction = (score - low) / (high - low)
                y = (
                    top + fraction * plot_height
                    if task == "kernel"
                    else top + (1 - fraction) * plot_height
                )
                points.append((x, y))
            if not points:
                continue
            point_text = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
            color = COLORS[condition]
            elements.append(
                f'<polyline class="line" stroke="{color}" points="{point_text}" '
                f'stroke-dasharray="{"6 4" if condition == "multi_island" else "none"}"/>'
            )
            elements.extend(
                f'<circle class="point" stroke="{color}" cx="{x:.1f}" cy="{y:.1f}" r="4"/>'
                for x, y in points
            )

    legend_y = 372
    for index, condition in enumerate(("global", "multi_island")):
        x = 390 + index * 150
        color = COLORS[condition]
        dash = ' stroke-dasharray="6 4"' if condition == "multi_island" else ""
        elements.append(
            f'<line x1="{x}" y1="{legend_y - 4}" x2="{x + 28}" y2="{legend_y - 4}" stroke="{color}" stroke-width="2.5"{dash}/>'
        )
        elements.append(
            f'<text class="legend" x="{x + 36}" y="{legend_y}">{escape(CONDITION_LABELS[condition])}</text>'
        )
    elements.append("</svg>")
    return "\n".join(elements) + "\n"


def contrast_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    means = mean_points(rows)
    output = []
    tasks = sorted({row["task"] for row in rows})
    counts = sorted({row["agent_count"] for row in rows if row["agent_count"] > 1})
    for task in tasks:
        for count in counts:
            global_score = means.get((task, "global", count))
            island_score = means.get((task, "multi_island", count))
            if global_score is None or island_score is None:
                continue
            advantage = (
                global_score - island_score
                if TASK_DIRECTIONS[task] == "minimize"
                else island_score - global_score
            )
            output.append(
                {
                    "task": task,
                    "agent_count": count,
                    "global_mean": global_score,
                    "multi_island_mean": island_score,
                    "multi_island_advantage": advantage,
                }
            )
    return output


def main() -> int:
    args = parse_args()
    results_root = args.results_root.resolve()
    command_paths = sorted(results_root.glob("**/operator-command.json"))
    if not command_paths:
        raise SystemExit(f"no run records found under {results_root}")
    audited_rows = [audit_run(path) for path in command_paths]
    rows, superseded, ineligible = select_complete_cells(audited_rows)
    repetitions = {int(row["repetition"]) for row in audited_rows}
    missing = expected_cell_identities(repetitions) - {cell_identity(row) for row in rows}
    if missing and not args.allow_incomplete:
        identities = ", ".join(
            f"{task}/{condition}/n={agent_count}/rep={repetition}"
            for task, condition, agent_count, repetition in sorted(missing)
        )
        raise SystemExit(f"incomplete cells: {identities}; pass --allow-incomplete to summarize")

    output_dir = args.output_dir.resolve()
    write_csv(output_dir / "results.csv", rows)
    contrasts = contrast_rows(rows)
    if contrasts:
        contrast_path = output_dir / "contrasts.csv"
        contrast_path.parent.mkdir(parents=True, exist_ok=True)
        with contrast_path.open("w", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=list(contrasts[0]), lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(contrasts)
    svg = chart_svg(rows)
    (output_dir / "performance.svg").write_text(svg)

    if not args.no_blog:
        write_csv(BLOG_DIR / "multi-island-scaling-results.csv", rows)
        (BLOG_DIR / "multi-island-scaling-performance.svg").write_text(svg)

    print(
        f"Audited {len(audited_rows)} runs; excluded {ineligible} incomplete, "
        f"protocol-invalid, or scoreless runs; superseded {superseded} duplicate "
        f"complete runs; retained {len(rows)} complete cells."
    )
    print(f"Wrote {output_dir / 'results.csv'}")
    if not args.no_blog:
        print(f"Wrote {BLOG_DIR / 'multi-island-scaling-results.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
