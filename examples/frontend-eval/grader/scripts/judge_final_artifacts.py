#!/usr/bin/env python3
"""Frozen-judge endpoint for Experiment 3.

For each finished run, take the LAST terminal commit from EVERY agent, judge
them all with the fixed four-criterion rubric, and emit one CSV row per
artifact. Primary endpoint per run is the maximum external score across its
agents; mean is secondary. Both are computed downstream, after judging.

    python scripts/judge_final_artifacts.py \\
        --label fixed    results/<slug>/<ts-a> \\
        --label evolving results/<slug>/<ts-b> \\
        --label random   results/<slug>/<ts-c> \\
        --out analysis/final_judgments.csv

Two things this deliberately does NOT do.

It does not pick each run's best-scoring attempt. That was the previous
behavior and it was a selection confound: the online score comes from the
rubric the run was using, so in the evolving arm the artifact chosen for
"external" judging was chosen BY the treatment. A run whose evolved rubric
happened to reward a weak page would nominate that page. Taking every agent's
terminal artifact removes the selection step entirely and yields four
observations per run instead of one.

It does not claim to be an external judge. It reuses this repository's
evaluator class, its rubric, and the same model family the arms scored with.
It is a development diagnostic with a known bias direction, useful for
detecting large effects quickly. A published third-party benchmark evaluator
is what the confirmatory claim needs, and `--judge` is where it plugs in.

Judging order is randomized across all artifacts from all runs (seeded, so it
is reproducible) so that any drift in the judge over a session cannot line up
with arm. Labels go to the CSV only; the judge never sees them. Roughly 2-4
minutes per artifact. Idempotent: existing (run, commit) rows are skipped
unless --force.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_evaluator.grader import AgenticEvaluator  # noqa: E402

from coral.config import GraderConfig  # noqa: E402
from coral.types import Task  # noqa: E402

FROZEN_CRITERIA = [
    {
        "name": "Design Quality",
        "weight": 3.0,
        "description": "Does the design feel like a coherent whole rather than a collection of parts?",
    },
    {
        "name": "Originality",
        "weight": 3.0,
        "description": "Is there evidence of custom decisions, or is this template layouts, "
        "library defaults, and AI-generated patterns?",
    },
    {
        "name": "Craft",
        "weight": 0.5,
        "description": "Technical execution: typography hierarchy, spacing consistency, color "
        "harmony, contrast ratios.",
    },
    {
        "name": "Functionality",
        "weight": 0.25,
        "description": "Usability independent of aesthetics.",
    },
]
EVALUATOR_MODEL = "claude-sonnet-4-5"  # pinned; must match the arms' configs
EVALUATOR_MAX_TURNS = 80


def terminal_artifacts(run_dir: Path) -> list[dict]:
    """Each agent's last non-archived *submitted* commit, whatever the online
    evaluation did.

    Selection is on submission time alone. Two things are deliberately NOT
    conditioned on:

    * **Score.** Picking the best-scoring attempt would let the treatment
      choose its own exhibit, since the online score comes from the rubric the
      run was using.
    * **Whether the online evaluation succeeded.** An attempt whose evaluator
      crashed or timed out still contains a real commit — the code is there and
      is exactly as judgeable as any other. Dropping those attempts conditions
      the sample on evaluator success, and evaluator failure is not evenly
      spread: in the 2026-09-03 Opus run the four failures fell on three of the
      four agents, with captain-ahab losing two (17% of its submissions). An
      agent whose last attempt crashed would have contributed an *older* page
      than its peers, which is a silent handicap correlated with nothing the
      experiment is measuring.

    Pending attempts count too: `pending` means the grader had not finished,
    not that the commit is absent.
    """
    latest: dict[str, dict] = {}
    for p in sorted((run_dir / ".coral" / "public" / "attempts").glob("*.json")):
        try:
            a = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if (a.get("metadata") or {}).get("archived"):
            continue
        if not a.get("commit_hash"):
            continue
        agent = a.get("agent_id") or "?"
        if agent not in latest or a["timestamp"] > latest[agent]["timestamp"]:
            latest[agent] = a
    return [
        {
            "agent": agent,
            "commit": a["commit_hash"],
            # Recorded for the record, never used to select. None when the
            # online evaluation never produced one.
            "online_score": None if a.get("score") is None else float(a["score"]),
            "online_status": a.get("status"),
            "timestamp": a["timestamp"],
        }
        for agent, a in sorted(latest.items())
    ]


def run_arm(run_dir: Path) -> str:
    """Read the arm from the private manifest, never from the path.

    The three arm configs share a task name on purpose, so the results
    directory no longer identifies the arm. The grader writes the manifest into
    `.coral/private/`, which agents cannot read.
    """
    p = run_dir / ".coral" / "private" / "run_manifest.json"
    try:
        return str(json.loads(p.read_text()).get("arm", "unknown"))
    except (OSError, json.JSONDecodeError):
        return "unknown"


def checkout(run_dir: Path, commit: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    tar = subprocess.run(
        ["git", "-C", str(run_dir / "repo"), "archive", commit], capture_output=True, check=True
    )
    subprocess.run(["tar", "-x", "-C", str(dest)], input=tar.stdout, check=True)


def task_text(run_dir: Path) -> tuple[str, str]:
    try:
        import yaml

        cfg = yaml.safe_load((run_dir / ".coral" / "config.yaml").read_text())
        return cfg["task"]["name"], cfg["task"]["description"]
    except Exception:
        return "Frontend task", ""


def judge(run_dir: Path, commit: str, work: Path) -> dict:
    site = work / "site"
    checkout(run_dir, commit, site)
    private = work / "private"
    private.mkdir()
    name, desc = task_text(run_dir)
    g = AgenticEvaluator(
        GraderConfig(
            entrypoint="agentic_evaluator.grader:AgenticEvaluator",
            timeout=1500,
            args={
                "evaluator_model": EVALUATOR_MODEL,
                "evaluator_max_turns": EVALUATOR_MAX_TURNS,
                "serve_port": 0,
                "session_persistent": False,  # fresh judge per artifact: no anchoring
                "criteria": FROZEN_CRITERIA,
                "task_name": name.split("(")[0].strip(),
                "task_description": desc,
                "evaluation_instructions": (
                    "The page is at {url}. Navigate it, take screenshots, test any "
                    "interactions, then score each criterion with concrete evidence cited."
                ),
            },
        )
    )
    g.private_dir = str(private)
    g.codebase_path = str(site)
    g.island_id = None
    g.tasks = [Task(id="judge", name=name, description=desc, metadata={"commit_hash": commit})]
    bundle = g.evaluate()
    row = {c["name"]: bundle.get_score_value(c["name"], float("nan")) for c in FROZEN_CRITERIA}
    row["aggregated"] = bundle.aggregated if bundle.aggregated is not None else float("nan")
    row["feedback"] = (bundle.feedback or "")[:4000]
    return row


FIELDS = [
    "judged_at",
    "label",
    "arm",
    "run",
    "agent",
    "commit",
    "online_score",
    "online_status",
    "judge_order",
    *[c["name"] for c in FROZEN_CRITERIA],
    "aggregated",
    "feedback",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument(
        "--label",
        action="append",
        default=[],
        help="label for the corresponding positional run (CSV only; judge never sees it)",
    )
    ap.add_argument("--out", type=Path, default=Path("analysis/final_judgments.csv"))
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--order-seed",
        type=int,
        default=0,
        help="seed for the randomized judging order (reproducible)",
    )
    a = ap.parse_args()
    labels = a.label + [""] * (len(a.runs) - len(a.label))

    # Build the full work list across every run, then shuffle it so judging
    # order is independent of arm. Judging all of one arm before another would
    # confound arm with any drift in the judge over the session.
    work: list[dict] = []
    for run_dir, label in zip(a.runs, labels, strict=True):
        arts = terminal_artifacts(run_dir)
        if not arts:
            print(f"warning: {run_dir} has no terminal scored attempts; skipping", file=sys.stderr)
        for art in arts:
            work.append(
                {
                    **art,
                    "run": str(run_dir),
                    "run_dir": run_dir,
                    "label": label,
                    "arm": run_arm(run_dir),
                }
            )
    random.Random(a.order_seed).shuffle(work)

    a.out.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if a.out.exists():
        with open(a.out) as f:
            existing = {(r["run"], r["commit"]) for r in csv.DictReader(f)}

    print(f"{len(work)} artifacts from {len(a.runs)} runs, judging in seeded random order\n")
    write_header = not a.out.exists()
    with open(a.out, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            w.writeheader()
        for i, item in enumerate(work, 1):
            if (item["run"], item["commit"]) in existing and not a.force:
                print(f"[{i}/{len(work)}] skip {item['commit'][:10]}: already judged")
                continue
            print(
                f"[{i}/{len(work)}] judging {item['commit'][:10]} "
                f"(agent {item['agent']}, online "
                + (
                    f"{item['online_score']:.3f}"
                    if item["online_score"] is not None
                    else f"n/a [{item['online_status']}]"
                )
                + ") ...",
                flush=True,
            )
            with tempfile.TemporaryDirectory(prefix="judge-") as tmp:
                row = judge(item["run_dir"], item["commit"], Path(tmp))
            w.writerow(
                {
                    "judged_at": datetime.now(UTC).isoformat(),
                    "label": item["label"],
                    "arm": item["arm"],
                    "run": item["run"],
                    "agent": item["agent"],
                    "commit": item["commit"],
                    "online_score": item["online_score"],
                    "online_status": item["online_status"],
                    "judge_order": i,
                    **row,
                }
            )
            f.flush()
            print(
                f"    -> aggregated {row['aggregated']:.3f}  "
                + "  ".join(f"{c['name']}={row[c['name']]:.2f}" for c in FROZEN_CRITERIA)
            )
    print(f"\nwrote {a.out}")
    print("Primary endpoint is max(aggregated) per run; mean is secondary. Compute both from")
    print("this CSV — neither is a selection rule applied before judging.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
