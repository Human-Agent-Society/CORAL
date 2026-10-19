#!/usr/bin/env python3
"""Generate the two arm configs (static, adaptive). Generated, never hand-written.

    python tools/make_configs.py [--model claude-opus-4-8] [--per-invocation-usd 15]

The `task:` block is byte-identical across arms; only `grader.args` differs,
and `grader.hide_args` keeps that block out of the config agents can read.

Machine-specific paths are not written into the configs. The owner-only data
root is read from the ``SKYSYNTH_PRIVATE`` environment variable at load time
(OmegaConf ``${oc.env:...}``): ``grader.private`` copies
``$SKYSYNTH_PRIVATE/router_private`` into the run and
``agents.sandbox.deny_read`` hides the whole root from builders. Loading a
config with the variable unset fails, which is the intended behaviour.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent

TASK_BLOCK = """task:
  name: "Two-tenant LLM router on a shared fleet"
  description: |
    Build one router per tenant for a shared, rate-limited fleet of twelve models on three
    providers. Tenant A is interactive (2.5 s time-to-first-token objective); tenant B is
    batch (ten-minute completion objective, cost-oriented). Deliver `solution.py` exporting
    `InteractiveRouter` and `BatchRouter`, each implementing `decide(req, now_ms, fleet_view)`
    from `evaluator/router_interface.py`, plus the informational `on_error` and `on_complete`.

    Read `README.md` and `task/task.md` first. Both routers run in ONE replay against ONE
    fleet; the harness dispatches each request to the router for `req.features["tenant"]`.

    Correctness is pass/fail and gates everything: any typed replay violation (lost request,
    illegal shed, illegal substitution, dispatching into an announced outage past grace,
    double completion, exception, nontermination) makes a submission invalid. Among valid
    submissions the training signal is U = mean_quality - late_rate - 3 * cost_per_request,
    reported per tenant and merged. Your router never sees ground-truth quality at decision
    time; `req.features["pred"]` carries the supplied predictor's per-model estimate.

    Validation and test traces are held by the harness owner. Submit `solution.py` and
    nothing else needs to change. Keep it self-contained: at evaluation it runs in a
    network-less process that can import only `evaluator.router_interface` and read `task/`.
  tips: |
    - Run `python tools/replay_pair.py solution.py data/trace_merged_train.jsonl` before
      every eval; it is the grader's projection, in-process.
    - Read the feedback's scenario checks. Each names the contract clause it tests and ships
      its full scenario JSON so you can reproduce a failure locally.
    - A correct slow router beats a fast invalid one: fix violations before tuning U.
"""

GRADER = """grader:
  entrypoint: {entrypoint}
  setup:
    # cwd for setup commands is this config's directory.
    - uv pip install -e ../../grader
  timeout: 900
  direction: maximize
  hide_args: true
  private:
    # Owner-only data root, read from the environment at load time. Holds the
    # TRAIN trace and the out-of-fold train predictions; val/test never enter a run.
    - ${{oc.env:SKYSYNTH_PRIVATE}}/router_private
  parallel:
    max_workers: 1
  args:
    arm: {arm}
    private_data_dir: router_private
    train_trace: traces/trace_merged_train.jsonl
    call_timeout_s: 5.0
    max_wall_ms: 300000
    # Training replays attach OUT-OF-FOLD predictions for train prompts (same
    # recipe as upstream's predictor, 5-fold refit; tools/refit_predictions_oof.py).
    # Upstream's table predicts train in sample, which gave builders a cleaner
    # signal than validation and test deliver. Val/test predictions and the
    # generic reference are unchanged.
    train_predictions: predictions_train_oof.json
{extra}
"""

STATIC_EXTRA = "    # Static arm: the fixed scenario suite for the whole run."

ADAPTIVE_EXTRA = """    # Adaptive arm: at fixed checkpoints on the finalized-attempt clock the
    # proposer is shown each builder's latest evaluated solution.py and its
    # training result and may propose at most two scenario checks per
    # checkpoint, six per run. Admission is mechanical: the reference pair
    # passes twice identically, the library mutant for the invariant fails,
    # and a cited candidate fails. No retirement, no reweighting, no tuning.
    checkpoints: [8, 12, 16]
    max_checks_per_checkpoint: 2
    max_checks_total: 6
    proposer_model: {model}
    proposer_max_turns: 20
    proposer_timeout: 600{proposer_cap}"""

AGENTS_RUN = """agents:
  count: 4
  runtime: claude_code
  model: {model}
  max_turns: 400
  research: false
{runtime_options}  sandbox:
    # OS-level builder isolation (Anthropic sandbox-runtime; Seatbelt on macOS).
    # Reads are confined to the run; $HOME is denied except the toolchain's own
    # dirs, and ~/.cache is one of those, which is why the private data root
    # must live outside it and is named here explicitly as well.
    # tools/probe_builder_isolation.py verifies this before every launch.
    enabled: true
    network: open
    deny_read:
      - ${{oc.env:SKYSYNTH_PRIVATE}}

workspace:
  # CORAL copies <config dir>/seed into the run repo when it exists; the `seed`
  # symlink beside each task.yaml points at ../../seed so the config works from
  # any working directory. repo_path is the same directory, for `coral validate`.
  repo_path: ../../seed

run:
  session: local
  stop:
    max_real_attempts: 24
"""

HEADER = """# GENERATED by examples/skysynth_router/tools/make_configs.py. Do not hand-edit.
# Arm: {arm}. The `task:` block is byte-identical across arms; only grader.args
# differs and grader.hide_args keeps it out of the agent-visible config.
# Requires SKYSYNTH_PRIVATE in the environment (see README.md, "Data").

"""

ENTRYPOINTS = {
    "static": "skysynth_router_grader.grader:RouterGrader",
    "adaptive": "skysynth_router_grader.evolving:AdaptiveRouterGrader",
}


def build(arm: str, model: str, per_invocation_usd: float | None) -> str:
    runtime_options = ""
    proposer_cap = ""
    if per_invocation_usd is not None:
        runtime_options = (
            "  runtime_options:\n"
            "    # Claude Code's own hard ceiling per invocation (--max-budget-usd). The\n"
            "    # launcher reserves this much for every live session against the run cap.\n"
            f"    max_budget_usd: {float(per_invocation_usd)}\n"
        )
        proposer_cap = f"\n    proposer_max_budget_usd: {float(per_invocation_usd)}"
    extra = (
        STATIC_EXTRA
        if arm == "static"
        else ADAPTIVE_EXTRA.format(model=model, proposer_cap=proposer_cap)
    )
    return (
        HEADER.format(arm=arm)
        + TASK_BLOCK
        + "\n"
        + GRADER.format(entrypoint=ENTRYPOINTS[arm], arm=arm, extra=extra)
        + "\n"
        + AGENTS_RUN.format(model=model, runtime_options=runtime_options)
    )


def write(arm: str, text: str, out_root: Path) -> Path:
    d = out_root / arm
    d.mkdir(parents=True, exist_ok=True)
    (d / "task.yaml").write_text(text)
    link = d / "seed"
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(os.path.relpath(HERE / "seed", d))
    return d / "task.yaml"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-opus-4-8", help="builder and proposer model")
    ap.add_argument(
        "--per-invocation-usd",
        type=float,
        default=15.0,
        help="Claude Code's --max-budget-usd per builder session and per proposer call; 0 disables",
    )
    ap.add_argument("--out", type=Path, default=HERE / "configs")
    a = ap.parse_args(argv)
    cap = a.per_invocation_usd if a.per_invocation_usd and a.per_invocation_usd > 0 else None
    for arm in ENTRYPOINTS:
        print(f"wrote {write(arm, build(arm, a.model, cap), a.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
