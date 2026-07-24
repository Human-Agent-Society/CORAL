#!/usr/bin/env python3
"""Audit and summarize the high-dimensional multi-island difficulty ladder.

The ladder has no exact oracle at N=128.  This report therefore keeps the
observed scalar score, reports a fixed operator-side greedy reference, and
labels the resulting ratio as *reference gain* rather than optimality.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import defaultdict
from html import escape
from pathlib import Path
from typing import Any

from experiments.multi_island import analyze as base

ROOT = Path(__file__).resolve().parent
TASKDATA = ROOT / "tasks/institutional_landscape/taskdata"
TASKS = ("smooth128", "rugged128_k4", "rugged128_k12", "rugged128_k24")
CONDITIONS = ("global", "partition", "multi_island")
TASK_LABELS = {
    "smooth128": "Smooth 128 (K=0)",
    "rugged128_k4": "Rugged 128 (K=4)",
    "rugged128_k12": "Rugged 128 (K=12)",
    "rugged128_k24": "Rugged 128 (K=24)",
}
COLORS = {"global": "#667085", "partition": "#D97706", "multi_island": "#0F766E"}
LABELS = {"global": "Global", "partition": "Partition", "multi_island": "Multi-island"}
EXPECTED_ATTEMPTS = 24
REPETITIONS = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-root",
        type=Path,
        default=Path("/var/tmp/coral-institutions-results/hard-ladder-v1"),
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "analysis")
    parser.add_argument("--diagnostics", type=Path, default=ROOT / "landscape_diagnostics.json")
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


def load_diagnostics(path: Path) -> dict[str, dict[str, float]]:
    data = json.loads(path.read_text())
    return {str(row["config"]).removesuffix(".json"): row for row in data["landscapes"]}


def configure_base() -> None:
    """Reuse the proven run/attempt parser with ladder-specific constants."""
    base.EXPECTED_ATTEMPTS = EXPECTED_ATTEMPTS
    base.MIGRATION_EVERY = max(6, EXPECTED_ATTEMPTS // 4)
    base.MIGRATION_RANK_WINDOW = max(6, EXPECTED_ATTEMPTS // 4)
    base.MIGRATION_COOLDOWN = 6
    base.REPETITIONS = REPETITIONS
    base.TASK_CONDITIONS = {task: CONDITIONS for task in TASKS}
    base.TASK_LABELS = TASK_LABELS
    base.CONDITION_LABELS = LABELS
    base.COLORS = COLORS

    def fitness(candidate: str, config_name: str) -> float:
        config = json.loads((TASKDATA / f"{config_name}.json").read_text())
        k, seed = int(config["k"]), str(config["seed"])
        total = 0.0
        for index in range(len(candidate)):
            pattern = "".join(
                candidate[(index + offset) % len(candidate)] for offset in range(k + 1)
            )
            digest = hashlib.sha256(f"{seed}:{index}:{pattern}".encode()).digest()
            total += int.from_bytes(digest[:8], "big") / 2**64
        return total / len(candidate)

    base.landscape_fitness = fitness
    base.BASELINES = {
        task: fitness("0" * int(json.loads((TASKDATA / f"{task}.json").read_text())["n"]), task)
        for task in TASKS
    }


def bootstrap(values: list[float], seed_text: str) -> tuple[float, float]:
    digest = hashlib.sha256(seed_text.encode()).digest()
    return base.bootstrap_ci(values, seed=int.from_bytes(digest[:8], "big"))


def normalized_gain(
    task: str, score: float | None, diagnostics: dict[str, dict[str, float]]
) -> float | None:
    if score is None:
        return None
    baseline = float(base.BASELINES[task])
    reference = float(diagnostics[task]["greedy_best_fitness"])
    denominator = reference - baseline
    return None if denominator <= 0 else (score - baseline) / denominator


def z_score(
    task: str, score: float | None, diagnostics: dict[str, dict[str, float]]
) -> float | None:
    if score is None:
        return None
    mean = float(diagnostics[task]["sample_mean"])
    sd = float(diagnostics[task]["sample_sd"])
    return None if sd <= 0 else (score - mean) / sd


def diversity(run: base.Run, count: int) -> float:
    latest: dict[str, base.Attempt] = {}
    for attempt in run.attempts[:count]:
        if attempt.candidate is not None:
            latest[attempt.agent_id] = attempt
    baseline_candidate = base.candidate_from_source(run.baseline_source)
    solutions = [
        latest.get(
            agent_id,
            base.Attempt(
                "seed",
                agent_id,
                base.BASELINES[run.task],
                "",
                run.baseline_source,
                baseline_candidate,
            ),
        )
        for agent_id in run.agent_ids
    ]
    distances = [
        base.source_distance(run.task, solutions[i].source, solutions[j].source)
        for i in range(len(solutions))
        for j in range(i + 1, len(solutions))
    ]
    return statistics.fmean(distances) if distances else 0.0


def score_progress(run: base.Run) -> list[float | None]:
    current = float(base.BASELINES[run.task])
    result: list[float | None] = []
    for attempt in run.attempts:
        if attempt.score is not None:
            current = max(current, attempt.score)
        result.append(current)
    return result


def runtime_errors(run: base.Run) -> int:
    """Count agent-runtime errors separately from grader protocol failures."""
    count = 0
    for path in run.path.glob(".coral/**/logs/*.log"):
        try:
            for line in path.read_text().splitlines():
                record = json.loads(line)
                if record.get("type") == "error":
                    count += 1
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
    return count


def run_row(run: base.Run, diagnostics: dict[str, dict[str, float]]) -> dict[str, Any]:
    progress = score_progress(run)
    scores = [float(x) for x in progress]
    final = scores[-1] if scores else float(base.BASELINES[run.task])
    normalized = normalized_gain(run.task, final, diagnostics)
    auc_values = [normalized_gain(run.task, score, diagnostics) for score in progress]
    auc = statistics.fmean(x for x in auc_values if x is not None)
    return {
        "task": run.task,
        "task_label": TASK_LABELS[run.task],
        "condition": run.condition,
        "repetition": run.repetition,
        "run_dir": str(run.path),
        "real_attempts_used": len(run.attempts),
        "numeric_scores": sum(attempt.score is not None for attempt in run.attempts),
        "null_scores": sum(attempt.score is None for attempt in run.attempts),
        "total_real_records": run.total_real,
        "overshoot": max(0, run.total_real - EXPECTED_ATTEMPTS),
        "grader_errors": run.grader_errors,
        "runtime_errors": runtime_errors(run),
        "tune_attempts": run.tune_attempts,
        "tune_protocol_violations": run.tune_protocol_violations,
        "migrations": run.migrations,
        "migration_eval_counts": "|".join(map(str, run.migration_eval_counts)),
        "baseline_score": base.BASELINES[run.task],
        "reference_score": diagnostics[run.task]["greedy_best_fitness"],
        "best_score": final,
        "reference_gain": normalized,
        "random_z": z_score(run.task, final, diagnostics),
        "best_so_far_auc_reference": auc,
        "diversity_eval_12": diversity(run, 12),
        "diversity_eval_24": diversity(run, 24),
        "configuration_errors": "; ".join(run.configuration_errors),
    }


def summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["task"], row["condition"])].append(row)
    output: list[dict[str, Any]] = []
    metrics = (
        "best_score",
        "reference_gain",
        "best_so_far_auc_reference",
        "random_z",
        "diversity_eval_24",
    )
    for task in TASKS:
        for condition in CONDITIONS:
            group = grouped[(task, condition)]
            if not group:
                continue
            item: dict[str, Any] = {"task": task, "condition": condition, "n": len(group)}
            for metric in metrics:
                values = [float(row[metric]) for row in group]
                low, high = bootstrap(values, f"{task}:{condition}:{metric}")
                item[f"{metric}_mean"] = statistics.fmean(values)
                item[f"{metric}_sd"] = statistics.stdev(values) if len(values) > 1 else 0.0
                item[f"{metric}_ci_low"] = low
                item[f"{metric}_ci_high"] = high
            item["null_scores_total"] = sum(int(row["null_scores"]) for row in group)
            item["runtime_errors_total"] = sum(int(row["runtime_errors"]) for row in group)
            item["migrations_total"] = sum(int(row["migrations"]) for row in group)
            item["migration_eval_counts"] = ";".join(row["migration_eval_counts"] for row in group)
            output.append(item)
    return output


def contrasts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["task"], row["condition"])].append(row)
    output: list[dict[str, Any]] = []
    for task in TASKS:
        for reference in ("global", "partition"):
            item: dict[str, Any] = {"task": task, "contrast": f"multi_island_minus_{reference}"}
            for metric in (
                "reference_gain",
                "best_so_far_auc_reference",
                "random_z",
                "diversity_eval_24",
            ):
                left = [float(x[metric]) for x in grouped[(task, "multi_island")]]
                right = [float(x[metric]) for x in grouped[(task, reference)]]
                item[f"{metric}_difference"] = statistics.fmean(left) - statistics.fmean(right)
                low, high = base.bootstrap_difference(
                    left,
                    right,
                    seed=int.from_bytes(
                        hashlib.sha256(f"{task}:{reference}:{metric}".encode()).digest()[:8], "big"
                    ),
                )
                item[f"{metric}_ci_low"], item[f"{metric}_ci_high"] = low, high
            output.append(item)
    for metric in ("reference_gain", "best_so_far_auc_reference", "random_z"):
        cells = {
            (task, condition): [float(x[metric]) for x in grouped[(task, condition)]]
            for task in TASKS
            for condition in CONDITIONS
        }
        # The smooth-to-rugged slope is descriptive; K is the declared ladder.
        for left_task, right_task in zip(TASKS, TASKS[1:], strict=True):
            for condition in ("global", "multi_island"):
                item = {
                    "task": f"{left_task}_to_{right_task}",
                    "contrast": f"{condition}_difficulty_step",
                }
                item[f"{metric}_difference"] = statistics.fmean(
                    cells[(right_task, condition)]
                ) - statistics.fmean(cells[(left_task, condition)])
                output.append(item)
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


def attempt_rows(runs: list[base.Run], diagnostics: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for run in runs:
        progress = score_progress(run)
        for index, (attempt, current) in enumerate(zip(run.attempts, progress, strict=True), 1):
            output.append(
                {
                    "task": run.task,
                    "condition": run.condition,
                    "repetition": run.repetition,
                    "evaluation": index,
                    "commit_hash": attempt.commit_hash,
                    "agent_id": attempt.agent_id,
                    "score": attempt.score,
                    "null": attempt.score is None,
                    "best_so_far": current,
                    "reference_gain_so_far": normalized_gain(run.task, current, diagnostics),
                }
            )
    return output


def svg_document(width: int, height: int, body: list[str], title: str) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(title)}</title>',
            '<desc id="desc">Run-level points, cell means, and descriptive replicate-bootstrap intervals.</desc>',
            "<style>text{font-family:Inter,ui-sans-serif,system-ui,sans-serif;fill:#1D2939}.axis{stroke:#98A2B3;stroke-width:1}.grid{stroke:#EAECF0;stroke-width:1}.mean{stroke:#101828;stroke-width:1.5}.ci{stroke:#344054;stroke-width:2}.point{stroke:white;stroke-width:1.2}</style>",
            *body,
            "</svg>",
            "",
        ]
    )


def panel_chart(
    rows: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    metric: str,
    title: str,
    ylabel: str,
    *,
    percent: bool = False,
) -> str:
    width, height = 1500, 430
    left, right, top, bottom, gap = 62, 24, 62, 88, 22
    panel_width = (width - left - right - gap * (len(TASKS) - 1)) / len(TASKS)
    index = {(row["task"], row["condition"]): row for row in summary}
    vals = [float(row[f"{metric}_mean"]) for row in summary]
    lows = [float(row[f"{metric}_ci_low"]) for row in summary]
    highs = [float(row[f"{metric}_ci_high"]) for row in summary]
    low, high = min([0.0, *vals, *lows]), max([0.0, *vals, *highs])
    pad = max((high - low) * 0.14, 0.05)
    low, high = low - pad, high + pad
    plot_height = height - top - bottom

    def y(value: float) -> float:
        return top + (high - value) / (high - low) * plot_height

    body = [
        f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>',
        f'<text x="{width / 2:.1f}" y="28" text-anchor="middle" font-size="19" font-weight="700">{escape(title)}</text>',
        f'<text transform="translate(17 {top + plot_height / 2:.1f}) rotate(-90)" text-anchor="middle" font-size="12">{escape(ylabel)}</text>',
    ]
    for pi, task in enumerate(TASKS):
        x0 = left + pi * (panel_width + gap)
        for ti in range(5):
            value = low + (high - low) * ti / 4
            yp = y(value)
            body += [
                f'<line class="grid" x1="{x0:.1f}" y1="{yp:.1f}" x2="{x0 + panel_width:.1f}" y2="{yp:.1f}"/>',
                f'<text x="{x0 - 7:.1f}" y="{yp + 4:.1f}" text-anchor="end" font-size="10">{value * 100 if percent else value:.2f}{"%" if percent else ""}</text>',
            ]
        body += [
            f'<line class="axis" x1="{x0:.1f}" y1="{top}" x2="{x0:.1f}" y2="{top + plot_height}"/>',
            f'<line class="axis" x1="{x0:.1f}" y1="{y(0):.1f}" x2="{x0 + panel_width:.1f}" y2="{y(0):.1f}"/>',
            f'<text x="{x0 + panel_width / 2:.1f}" y="48" text-anchor="middle" font-size="13" font-weight="650">{escape(TASK_LABELS[task])}</text>',
        ]
        slot = panel_width / len(CONDITIONS)
        task_rows = [row for row in rows if row["task"] == task]
        for ci, condition in enumerate(CONDITIONS):
            center = x0 + slot * (ci + 0.5)
            item = index[(task, condition)]
            body += [
                f'<line class="ci" x1="{center:.1f}" y1="{y(float(item[f"{metric}_ci_low"])):.1f}" x2="{center:.1f}" y2="{y(float(item[f"{metric}_ci_high"])):.1f}"/>',
                f'<line class="mean" x1="{center - 13:.1f}" y1="{y(float(item[f"{metric}_mean"])):.1f}" x2="{center + 13:.1f}" y2="{y(float(item[f"{metric}_mean"])):.1f}"/>',
            ]
            for oi, row in enumerate([r for r in task_rows if r["condition"] == condition]):
                body.append(
                    f'<circle class="point" cx="{center + (-7, 0, 7)[oi % 3]:.1f}" cy="{y(float(row[metric])):.1f}" r="4.2" fill="{COLORS[condition]}"/>'
                )
            body.append(
                f'<text transform="translate({center - 2:.1f} {height - bottom + 18}) rotate(-35)" text-anchor="end" font-size="10">{LABELS[condition]}</text>'
            )
    return svg_document(width, height, body, title)


def difficulty_chart(summary: list[dict[str, Any]], metric: str, title: str, ylabel: str) -> str:
    width, height = 900, 450
    left, right, top, bottom = 72, 35, 65, 74
    pw, ph = width - left - right, height - top - bottom
    index = {(row["task"], row["condition"]): row for row in summary}
    values = [
        float(index[(task, condition)][f"{metric}_mean"])
        for task in TASKS
        for condition in CONDITIONS
    ]
    low, high = min([0.0, *values]), max([0.0, *values])
    pad = max((high - low) * 0.16, 0.05)
    low, high = low - pad, high + pad

    def x(i: int) -> float:
        return left + pw * i / (len(TASKS) - 1)

    def y(v: float) -> float:
        return top + (high - v) / (high - low) * ph

    body = [
        f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>',
        f'<text x="{width / 2:.1f}" y="29" text-anchor="middle" font-size="19" font-weight="700">{escape(title)}</text>',
        f'<text transform="translate(18 {top + ph / 2:.1f}) rotate(-90)" text-anchor="middle" font-size="12">{escape(ylabel)}</text>',
    ]
    for ti in range(5):
        value = low + (high - low) * ti / 4
        yp = y(value)
        body += [
            f'<line class="grid" x1="{left}" y1="{yp:.1f}" x2="{width - right}" y2="{yp:.1f}"/>',
            f'<text x="{left - 9}" y="{yp + 4:.1f}" text-anchor="end" font-size="10">{value:.2f}</text>',
        ]
    body.append(f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + ph}"/>')
    for condition in CONDITIONS:
        points = [
            (x(i), y(float(index[(task, condition)][f"{metric}_mean"])))
            for i, task in enumerate(TASKS)
        ]
        body.append(
            f'<path d="M {points[0][0]:.1f} {points[0][1]:.1f} '
            + " ".join(f"L {px:.1f} {py:.1f}" for px, py in points[1:])
            + f'" fill="none" stroke="{COLORS[condition]}" stroke-width="3"/>'
        )
        for px, py in points:
            body.append(
                f'<circle class="point" cx="{px:.1f}" cy="{py:.1f}" r="6" fill="{COLORS[condition]}"/>'
            )
    for i, task in enumerate(TASKS):
        body.append(
            f'<text x="{x(i):.1f}" y="{height - bottom + 25}" text-anchor="middle" font-size="11">{TASK_LABELS[task]}</text>'
        )
    for i, condition in enumerate(CONDITIONS):
        xx = left + 10 + i * 180
        body += [
            f'<line x1="{xx}" y1="48" x2="{xx + 20}" y2="48" stroke="{COLORS[condition]}" stroke-width="3"/>',
            f'<text x="{xx + 27}" y="52" font-size="11">{LABELS[condition]}</text>',
        ]
    return svg_document(width, height, body, title)


def main() -> int:
    args = parse_args()
    configure_base()
    diagnostics = load_diagnostics(args.diagnostics)
    runs, incomplete = base.discover_runs(args.results_root.resolve())
    expected = len(TASKS) * len(CONDITIONS) * REPETITIONS
    if len(runs) != expected and not args.allow_incomplete:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "incomplete-runs.json").write_text(
            json.dumps(incomplete, indent=2) + "\n"
        )
        raise SystemExit(f"Matrix incomplete: found {len(runs)}/{expected} complete cells")
    rows = [run_row(run, diagnostics) for run in runs]
    summary = summaries(rows)
    contrast = contrasts(rows) if len(runs) == expected else []
    integrity: list[dict[str, Any]] = []
    for run in runs:
        reasons = list(run.configuration_errors)
        try:
            identity = json.loads((run.path / "operator-command.json").read_text())
            command = identity.get("command", [])
            role_setting = next(
                (item for item in command if str(item).startswith("agents.runtime_options.role_file=")),
                "",
            )
            expected_role = f"agents.runtime_options.role_file={ROOT / 'eval_protocol.md'}"
            if role_setting != expected_role:
                reasons.append(f"role protocol={role_setting!r}, expected hard 24-eval protocol")
        except (OSError, json.JSONDecodeError, AttributeError, TypeError):
            reasons.append("operator command is unreadable")
        private_path = run.path / ".coral" / "private" / f"{run.task}.json"
        frozen_path = TASKDATA / f"{run.task}.json"
        if not private_path.is_file() or private_path.read_bytes() != frozen_path.read_bytes():
            reasons.append("private landscape does not match frozen taskdata")
        if run.grader_errors:
            reasons.append(f"{run.grader_errors} grader infrastructure error(s)")
        if run.tune_protocol_violations:
            reasons.append(f"{run.tune_protocol_violations} tune protocol violation(s)")
        if run.condition != "multi_island" and run.migrations:
            reasons.append("migration note recorded in no-migration condition")
        if run.total_real != EXPECTED_ATTEMPTS:
            reasons.append(f"total real records={run.total_real}, expected {EXPECTED_ATTEMPTS}")
        # Runtime/API errors are retained as an audit metric but do not
        # invalidate a cell when the manager successfully completes its fixed
        # real-evaluation budget.
        if reasons:
            integrity.append(
                {
                    "task": run.task,
                    "condition": run.condition,
                    "repetition": run.repetition,
                    "run_dir": str(run.path),
                    "reasons": reasons,
                }
            )
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "runs.csv", rows)
    write_csv(output / "summary.csv", summary)
    write_csv(output / "contrasts.csv", contrast)
    write_csv(output / "attempts.csv", attempt_rows(runs, diagnostics))
    audit = {
        "schema_version": 1,
        "expected_cells": expected,
        "complete_cells": len(runs),
        "expected_attempts_per_cell": EXPECTED_ATTEMPTS,
        "reference_method": "fixed diagnostic multi-start greedy ascent; approximate, not global optimum",
        "diagnostics": diagnostics,
        "integrity_failures": integrity,
        "incomplete_or_superseded_runs": incomplete,
    }
    (output / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    if len(runs) != expected:
        print(f"Audited {len(runs)}/{expected} complete cells; no figures generated")
        return 0
    if integrity:
        raise SystemExit(
            f"Integrity audit failed for {len(integrity)} cell(s); see {output / 'audit.json'}"
        )
    (output / "performance.svg").write_text(
        panel_chart(
            rows,
            summary,
            "reference_gain",
            "High-dimensional performance relative to declared reference",
            "Fraction of reference gain",
        )
    )
    (output / "difficulty-topology.svg").write_text(
        difficulty_chart(
            summary, "reference_gain", "Difficulty ladder × topology", "Fraction of reference gain"
        )
    )
    (output / "diversity.svg").write_text(
        panel_chart(
            rows,
            summary,
            "diversity_eval_24",
            "Solution diversity after 24 real evaluations",
            "Mean pairwise Hamming distance",
            percent=True,
        )
    )
    (output / "migration-compliance.csv").write_text(
        "task,condition,repetition,migrations,migration_eval_counts,null_scores,runtime_errors,overshoot\n"
        + "\n".join(
            f'{r["task"]},{r["condition"]},{r["repetition"]},{r["migrations"]},"{r["migration_eval_counts"]}",{r["null_scores"]},{r["runtime_errors"]},{r["overshoot"]}'
            for r in rows
        )
        + "\n"
    )
    print(f"Analyzed {len(runs)}/{expected} complete cells")
    print(f"Run table: {output / 'runs.csv'}")
    print(f"Summary:   {output / 'summary.csv'}")
    print(f"Contrasts: {output / 'contrasts.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
