#!/usr/bin/env python3
"""Generate a CORAL task config for one UI-Bench task in one arm.

    python make_task.py --id 2 --arm adaptive --model haiku --attempts 24
    python make_task.py --id 2 --arm yoked --schedule ../../sched/adaptive-2.json
    python make_task.py --id 2 --arm static

Writes ``configs/<name>/task.yaml`` (default name ``<task>_<arm>``). CORAL validates
a task *directory* and requires the config to be named ``task.yaml``, so each run
config gets its own directory.

Generated, never hand-written. The three arms must be identical in everything
an agent can see, and hand-maintaining near-copies is exactly how the previous
generation of these configs drifted until their task names announced their own
conditions. Here the arm touches only `grader.args.evolution`; the whole `task:`
block is a pure function of the UI-Bench row, so it is byte-identical across
arms by construction.

Prompts come from the pinned dataset revision. The task name carries the
UI-Bench title and nothing about the arm, and `grader.hide_args` keeps the
evolution config out of the file agents can read.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
#: The prompt table is not redistributed here (the dataset card declares no
#: license). It is fetched once from the pinned dataset revision, verified
#: against the recorded digest, and cached under an ignored directory.
DATASET_REPO = "AfterQuery/ui-bench"
DATASET_REVISION = "3a8ec80d04b1498fbf12d275bbc5717413841015"
#: The file name in the dataset repository literally contains "%20".
DATASET_FILE = "UI-Bench%20Prompts%20-%20Main.csv"
DATASET_SHA256 = "a36f5e1ac51c5d8cb72f33fe78df539babb5a8976f906b0cdc96cd896361c51d"
DATASET_URL = (
    f"https://huggingface.co/datasets/{DATASET_REPO}/resolve/{DATASET_REVISION}/"
    + urllib.parse.quote(DATASET_FILE)
)
CSV = HERE / ".cache" / "ui_bench_prompts_main.csv"

# Appended unchanged to every task in every arm.
COMMON_INSTRUCTION = (
    "External services, email delivery, payments, uploads, generated links, and "
    "downloads may be represented by realistic local simulations. No external "
    "credentials or live transactions are required."
)

# The ten confirmatory tasks. The pilot must not use these.
CONFIRMATORY_IDS = {1, 5, 7, 11, 14, 17, 21, 23, 27, 29}

# Seed rubric adapted from LiveEvalBench, frozen with 0-1 anchors. All weight 1.0:
# the proposer cannot choose weights and expansion_weight matches, so the rubric
# stays unweighted and a criterion added late counts exactly like a seed one.
SEED_CRITERIA = [
    (
        "Build Smoothness",
        "The project installs, launches, and renders through the standard command "
        "without fatal build, runtime, or console errors.",
    ),
    (
        "Implementation Quality",
        "The code and state-management approach are coherent, maintainable, and "
        "appropriate for the required behavior.",
    ),
    (
        "Instruction Following",
        "The artifact satisfies the explicit scenario, goal, vibe, constraints, and "
        "common experimental instruction.",
    ),
    (
        "Visual Quality",
        "Layout, hierarchy, typography, color, spacing, consistency, and responsive "
        "behavior support a polished client-facing result.",
    ),
    (
        "Interaction Experience",
        "Required controls and workflows operate predictably, communicate state, "
        "prevent avoidable errors, and permit recovery.",
    ),
]

SCORE_ANCHORS = (
    "Score each criterion from 0 to 1. 0 is absent or unusable performance, 0.5 is "
    "partial performance with material deficiencies, and 1 is complete and "
    "high-quality performance supported by concrete browser or code evidence."
)


class PromptTableUnavailable(RuntimeError):
    """The pinned prompt table is neither cached nor fetchable."""


def prompt_table(path: Path = CSV) -> Path:
    """Return the pinned prompt table, fetching and caching it on first use.

    The bytes are verified against ``DATASET_SHA256`` both after a fetch and on
    every later read, so a config can only ever be generated from the exact
    revision its header records.
    """
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(DATASET_URL, timeout=60) as resp:  # noqa: S310
                data = resp.read()
        except (urllib.error.URLError, OSError) as exc:
            raise PromptTableUnavailable(f"could not fetch {DATASET_URL}: {exc}") from exc
        if hashlib.sha256(data).hexdigest() != DATASET_SHA256:
            raise PromptTableUnavailable(
                f"{DATASET_URL} does not match the recorded sha256 {DATASET_SHA256}"
            )
        path.write_bytes(data)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != DATASET_SHA256:
        raise PromptTableUnavailable(
            f"{path} has sha256 {digest}, expected {DATASET_SHA256}; delete it and rerun"
        )
    return path


def load_row(task_id: int) -> dict:
    rows = list(csv.DictReader(open(prompt_table(), encoding="utf-8")))
    for i, r in enumerate(rows, 1):
        if i == task_id:
            return r
    raise SystemExit(f"no UI-Bench row {task_id} (file has {len(rows)})")


def brief(row: dict) -> str:
    parts = [row["Scenario"].strip()]
    if row.get("Vibe", "").strip():
        parts.append(f"Vibe: {row['Vibe'].strip()}")
    if row.get("Constraints", "").strip():
        parts.append(f"Constraints: {row['Constraints'].strip()}")
    parts.append(COMMON_INSTRUCTION)
    parts.append("Entry point: index.html in the repo.")
    return "\n\n".join(parts)


def indent(text: str, n: int) -> str:
    pad = " " * n
    return "\n".join(pad + ln if ln.strip() else "" for ln in text.splitlines())


#: Attempts of exposure a publication must leave behind it.
MIN_POST_PUBLICATION_ATTEMPTS = 5
#: Scored-observation indices at which the adaptive proposer is invoked.
DEFAULT_CHECKPOINTS = [8, 12, 16]


def build(
    task_id: int,
    arm: str,
    model: str,
    attempts: int,
    schedule: str | None,
    window: int = 3,
    checkpoints: list[int] | None = None,
    brief_override: tuple[str, str] | None = None,
) -> str:
    """``brief_override`` is ``(name, text)``: it replaces the brief and the
    task name and nothing else, so a task built with one differs from its
    UI-Bench sibling in the brief alone. Everything an agent can otherwise see
    -- tips, seed criteria, hide_args -- is still generated here."""
    row = load_row(task_id)
    latest_pub = attempts - MIN_POST_PUBLICATION_ATTEMPTS
    checkpoints = checkpoints or DEFAULT_CHECKPOINTS

    if arm == "static":
        evolution = """      # Static arm: the five seed criteria stand for the whole run. Same grader
      # class, same retry path, same failure handling as the evolving arms.
      mode: static"""
    elif arm == "adaptive":
        cp = ", ".join(str(c) for c in checkpoints)
        evolution = f"""      # Adaptive arm: the proposer is invoked at fixed checkpoints on the
      # scored-observation clock and shown the last `window` scored attempts
      # (feedback, staged artifacts, agents' notes). Whether and what it
      # publishes depends on the trajectory; when it looks does not.
      mode: adaptive
      checkpoints: [{cp}]
      max_criteria: 11
      # Real-attempt bound, not the schedule: a checkpoint can never publish
      # with no attempts left to be exposed to.
      latest_publication_attempt: {latest_pub}
      window: {window}
      max_new_criteria_per_round: 2"""
    else:
        if not schedule:
            raise SystemExit("--schedule is required for the yoked arm")
        evolution = f"""      # Yoked arm: replays the paired adaptive run's checkpoint outcomes (same
      # checkpoints, same accepted counts) with a proposer that sees the brief
      # and the rubric only -- no artifacts, scores, feedback, notes or
      # transcripts. Same proposer model, same schema, same filters, same weights.
      mode: yoked
      yoked_schedule_file: {schedule}
      max_criteria: 11"""

    common = """
      # Every admitted criterion carries the seed weight, so the arms differ in
      # what criteria say, not in how much they count.
      expansion_weight: 1.0
      # The proposer is a separate role from the online evaluator: a stronger
      # model may propose without changing the judge that produces the score
      # trajectory both arms are measured against.
      proposer_model: claude-opus-5
      proposer_timeout: 600
      agent_notes_enabled: true
      agent_notes_char_budget: 4000
      max_evaluation_retries: 1"""

    task_name, task_brief = (
        brief_override
        if brief_override is not None
        else (f"UI-Bench {task_id}: {row['Title'].strip()}", brief(row))
    )

    crit_yaml = "\n".join(
        f'      - name: "{n}"\n        weight: 1.0\n        description: |\n{indent(d, 10)}'
        for n, d in SEED_CRITERIA
    )

    return f"""# UI-Bench task {task_id} — {row["Title"].strip()} ({row["Category"]}, {row["Type"]})
# GENERATED by examples/uibench/make_task.py. Do not hand-edit.
#
# Arm: {arm}. The `task:` block is a pure function of the UI-Bench row and is
# byte-identical across all three arms; only grader.args.evolution differs, and
# grader.hide_args keeps that out of the config agents can read.
#
# Prompt source: {DATASET_REPO} "{DATASET_FILE}" at revision
#   {DATASET_REVISION}
# Source file sha256: {DATASET_SHA256} (fetched and verified by make_task.py, not redistributed)
# {"CONFIRMATORY TASK" if task_id in CONFIRMATORY_IDS else "Excluded from the ten confirmatory tasks — pilot use only."}

task:
  name: "{task_name}"
  description: |
{indent(task_brief, 4)}
  tips: |
    - You have the `frontend-design` skill. Use it before writing any code.
    - After each eval, decide: refine or pivot. A pivot means a fundamentally
      different page, not a CSS rewrite.
    - Read the grading feedback for the criteria actually applied to your
      latest attempt before deciding what to change.

grader:
  entrypoint: agentic_evaluator.evolution:EvolvingAgenticEvaluator
  setup:
    # cwd for setup commands is this config's directory.
    - uv pip install -e ../../frontend-eval/grader
  timeout: 1500
  direction: maximize
  hide_args: true
  parallel:
    max_workers: 4
  args:
    evaluator_model: claude-sonnet-4-5
    evaluator_max_turns: 80
    serve_port: 0
    session_persistent: false
    evaluation_instructions: |
      The page is at {{url}}. Navigate it, take screenshots, test the required
      interactions, then score each criterion with concrete evidence cited.
      Save every screenshot into {{scratch_dir}} with a descriptive filename.

      {SCORE_ANCHORS}
    evolution:
{evolution}{common}
    criteria:
{crit_yaml}

agents:
  count: 4
  runtime: claude_code
  model: {model}
  max_turns: 400
  research: false
  skills:
    - "../../frontend-eval/skills/frontend-design"

workspace:
  repo_path: ../../frontend-eval/seed

run:
  session: local
  stop:
    max_real_attempts: {attempts}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", type=int, required=True)
    ap.add_argument("--arm", choices=("static", "adaptive", "yoked"), required=True)
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--attempts", type=int, default=24)
    ap.add_argument("--schedule", help="path to the paired adaptive run's schedule JSON")
    ap.add_argument(
        "--window",
        type=int,
        default=3,
        help="scored attempts shown to the proposer at a checkpoint",
    )
    ap.add_argument(
        "--checkpoints",
        help="comma-separated scored-attempt checkpoints for the adaptive arm "
        "(e.g. 8,12,16); switches it off the variance/entropy trigger",
    )
    ap.add_argument(
        "--brief-file",
        type=Path,
        help="replace the UI-Bench brief with this file's text (everything else "
        "-- rubric, arms, budget, tips -- is still generated identically)",
    )
    ap.add_argument("--task-name", help="task name to use with --brief-file")
    ap.add_argument("--name", help="output directory name (default <id>_<arm>)")
    ap.add_argument("-o", "--out", type=Path)
    a = ap.parse_args()

    try:
        prompt_table()
    except PromptTableUnavailable as exc:
        raise SystemExit(str(exc)) from exc
    checkpoints = [int(c) for c in a.checkpoints.split(",")] if a.checkpoints else None
    override = None
    if a.brief_file:
        if not a.task_name:
            raise SystemExit("--task-name is required with --brief-file")
        override = (a.task_name, a.brief_file.read_text().strip())
    text = build(a.id, a.arm, a.model, a.attempts, a.schedule, a.window, checkpoints, override)
    out = a.out or HERE / (a.name or f"{a.id:02d}_{a.arm}") / "task.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    if a.out is None:
        # CORAL resolves workspace.repo_path against the working directory but
        # copies <config dir>/seed into the run repo whenever it exists, so the
        # symlink is what makes the config work from any working directory.
        link = out.parent / "seed"
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(os.path.relpath(HERE.parent / "frontend-eval" / "seed", out.parent))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
