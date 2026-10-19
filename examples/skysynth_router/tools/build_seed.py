#!/usr/bin/env python3
"""Assemble the builder-visible ``seed/`` and the owner-only ``router_private/``.

    python tools/build_seed.py [--private $SKYSYNTH_PRIVATE] [--refit <predictions_refit.json>] [--check]

Inputs: the vendored ``upstream/`` (``tools/prepare_data.py vendor``), the
traces generated under ``$SKYSYNTH_PRIVATE/build`` (``prepare_data.py traces``)
and the out-of-fold refit table (``tools/refit_predictions_oof.py``, default
``$SKYSYNTH_PRIVATE/refit/predictions_refit.json``). Outputs: ``seed/`` (the
static files are committed; ``seed/data/`` is not) and
``$SKYSYNTH_PRIVATE/router_private/`` with the train trace, the out-of-fold
table the grader attaches in training replays, and a manifest. ``--check``
rebuilds nothing and compares the current seed against ``SEED_MANIFEST.json``.

What builders get, and why each item is public:

* ``solution.py`` -- the correct reference pair as a starting point (slow and
  expensive by design; valid, so attempt zero is a valid candidate).
* ``evaluator/router_interface.py`` -- the public interface (no quality fields).
* ``task/`` -- task text, the frozen env card, both workload cards, the fleet
  list, and upstream's generic policy and reference router for reading.
* ``data/trace_merged_train.jsonl`` -- the TRAIN split with its measured
  per-model quality. These are training labels ("fit on train", task.md); the
  boundary removes quality at decision time in every evaluation, and val/test
  never leave the owner side.
* ``data/predictions_train.json`` -- the predictor's scores for TRAIN prompt
  ids only, OUT OF FOLD (5-fold refit of upstream's recipe), plus its train-mean
  costs. Val/test predictions are attached per request by the trusted runtime,
  so no builder holds a table of future ids.
* ``tools/replay_pair.py`` and a copy of upstream's replay -- the public local
  replay, through the same projection the grader uses.

Nothing from val or test, and nothing from the raw benchmark archive, is
written here. The script refuses to run if it would.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
UPSTREAM = HERE / "upstream"
SEED = HERE / "seed"
GRADER_SRC = HERE / "grader" / "src" / "skysynth_router_grader"

sys.path.insert(0, str(GRADER_SRC.parent))
from skysynth_router_grader.mutants import REFERENCE_SOLUTION  # noqa: E402

README = """# SkySynth two-tenant router: what you are building

Read `task/task.md` first. It is the contract you are scored against.

## Deliverable

`solution.py` exporting two classes, `InteractiveRouter` (tenant A) and
`BatchRouter` (tenant B), each a `Router` from `evaluator.router_interface`.
Both run in **one** replay against **one** shared fleet; the harness routes
each request's `decide`, `on_error` and `on_complete` to the instance for
`req.features["tenant"]`.

Keep `solution.py` self-contained. At evaluation it runs in a separate,
network-less process whose working directory holds exactly this layout:
`solution.py`, `evaluator/router_interface.py`, and `task/` (env card,
workload cards, task text). Nothing else is importable or readable.

## What you can see, and what you cannot

* `data/trace_merged_train.jsonl` is the training split, with measured
  per-model `quality` for each prompt. Fit on it however you like.
* At **decision time** your router never sees `quality`. The `Request` you
  receive has no such field. A policy that worked locally by reading it will
  fail under the grader.
* `req.features["pred"]` carries the supplied predictor's score for each
  fleet model on this prompt, when available. `data/predictions_train.json`
  has the same numbers for training prompts, plus per-model train-mean cost.
  These training predictions are **out of fold**: the predictor was refit five
  times on 80% of the train prompts and each prompt's scores come from the fit
  that did not see it. Their agreement with the measured `quality` is what the
  predictor achieves on prompts it has not seen, which is also what it will
  achieve on the held-out validation and test splits. Treat `pred` as a noisy
  signal, not a label, and check on `trace_merged_train.jsonl` how much to
  trust it per task.
* Validation and test traces are held by the harness owner and are never
  available to you. Do not try to reconstruct them.

## Score

Correctness is pass/fail and gates everything: any typed violation in the
replay (lost request, illegal shed, illegal substitution, outage_lost,
double completion, exception) makes the candidate invalid. Among valid
candidates the training signal is the merged utility

    U = mean_quality - 1.0 * late_rate - 3.0 * cost_usd_per_request

reported per tenant and merged. Your feedback names every violation kind and
gives the per-tenant books.

## Local replay

    python tools/replay_pair.py solution.py data/trace_merged_train.jsonl

runs the same projection the grader uses (quality removed, predictions
attached) in-process, and prints the same books. Scenario checks the grader
applies are listed in your feedback with their full scenario so you can
reproduce them with `tools/replay_pair.py --check <check.json>`.
"""

REPLAY_TOOL = '''#!/usr/bin/env python3
"""Public local replay of a policy pair, through the grader's projection.

    python tools/replay_pair.py solution.py data/trace_merged_train.jsonl [--json]
    python tools/replay_pair.py solution.py --check some_check.json

In-process (no sandbox) but otherwise identical to the grader: quality is
removed from every request before your router sees it, predictions are
attached to features, both tenants share one replay, and the books are
upstream's own. Split is always the training mode (no outage windows) unless
a check specifies otherwise.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE / "upstream_replay"))
sys.path.insert(0, str(ROOT))

from evaluator.benchmark.replay_tenants import TenantReplay  # noqa: E402

PRIVATE = ("quality", "quality_floor")


def load_pair(path):
    spec = importlib.util.spec_from_file_location("solution", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["solution"] = mod
    spec.loader.exec_module(mod)
    return {"A": mod.InteractiveRouter(), "B": mod.BatchRouter()}


class LocalPairRouter:
    """Same dispatch and projection as the grader, minus the process boundary."""

    def __init__(self, routers, pred, fleet):
        self.routers, self.pred, self.fleet = routers, pred, fleet
        self._pub = {}

    def _public(self, req):
        p = self._pub.get(id(req))
        if p is None:
            from evaluator.router_interface import Request

            d = {k: v for k, v in req.__dict__.items() if k not in PRIVATE}
            feats = dict(d.get("features") or {})
            scores = self.pred.get(str(feats.get("prompt_id")))
            if scores is not None:
                feats["pred"] = {m: float(s) for m, s in zip(self.fleet, scores)}
            d["features"] = feats
            p = self._pub[id(req)] = Request(**d)
        return p

    def _r(self, req):
        return self.routers[req.features["tenant"]]

    def decide(self, req, now_ms, fleet_view):
        return self._r(req).decide(self._public(req), now_ms, fleet_view)

    def on_error(self, req, now_ms, kind, retry_after_ms):
        return self._r(req).on_error(self._public(req), now_ms, kind, retry_after_ms)

    def on_complete(self, req, now_ms):
        try:
            return self._r(req).on_complete(self._public(req), now_ms)
        finally:
            self._pub.pop(id(req), None)


def books(res):
    n = res["requests"]
    viol = sum(res["slo_violations"].values())
    lost = n - res["completed"] - res["shed"]
    rate = (viol + res["shed"] + lost) / n
    u = res["mean_quality"] - rate - 3.0 * res["total_cost_usd"] / n
    out = {
        "valid": res["violation_count"] == 0 and not res["aborted"],
        "violation_kinds": res["violation_kinds"],
        "merged": {
            "mean_quality": res["mean_quality"],
            "cost_usd": res["total_cost_usd"],
            "late_rate": round(rate, 4),
            "U": round(u, 4),
        },
        "tenants": {},
    }
    for t, b in res["tenants"].items():
        u = (b["mean_quality"] or 0) - b["slo_violation_rate"] - 3.0 * b["cost_usd"] / b["requests"]
        out["tenants"][t] = {
            "mean_quality": b["mean_quality"],
            "cost_usd": b["cost_usd"],
            "late_rate": b["slo_violation_rate"],
            "U": round(u, 4),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("solution")
    ap.add_argument("trace", nargs="?")
    ap.add_argument("--check", help="a check JSON from your feedback")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    art = json.load(open(ROOT / "data" / "predictions_train.json"))
    pred, fleet = art["pred"], art["fleet"]
    routers = load_pair(a.solution)
    if a.check:
        import tempfile

        import yaml

        c = json.load(open(a.check))
        d = Path(tempfile.mkdtemp())
        trace = d / "scenario.jsonl"
        trace.write_text("".join(json.dumps(r) + "\\n" for r in c["requests"]))
        card = d / "env_card.yaml"
        card.write_text(yaml.safe_dump(c["card"]))
        res = TenantReplay(str(card), split=c.get("split", "val")).run(
            str(trace), LocalPairRouter(routers, {}, [])
        )
    else:
        if not a.trace:
            ap.error("trace is required without --check")
        res = TenantReplay(str(ROOT / "task" / "env_card.yaml"), split="none").run(
            a.trace, LocalPairRouter(routers, pred, fleet)
        )
    out = books(res)
    print(json.dumps(out if not a.json else {"books": out, "upstream": res}, indent=2))


if __name__ == "__main__":
    main()
'''


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private_root(arg: Path | None) -> Path:
    root = arg or (
        Path(os.environ["SKYSYNTH_PRIVATE"]) if os.environ.get("SKYSYNTH_PRIVATE") else None
    )
    if root is None:
        raise SystemExit("pass --private or set SKYSYNTH_PRIVATE (the owner-only data root)")
    return root.resolve()


def check(seed: Path = SEED) -> list[str]:
    """Differences between the seed on disk and the committed SEED_MANIFEST.json."""
    manifest_path = seed / "SEED_MANIFEST.json"
    if not manifest_path.is_file():
        return ["SEED_MANIFEST.json missing"]
    want = json.loads(manifest_path.read_text())
    problems = []
    for rel, digest in want.items():
        p = seed / rel
        if not p.is_file():
            problems.append(f"missing {rel}")
        elif sha(p) != digest:
            problems.append(f"differs {rel}")
    for p in sorted(seed.rglob("*")):
        rel = p.relative_to(seed).as_posix()
        if (
            p.is_file()
            and rel not in want
            and rel != "SEED_MANIFEST.json"
            and "__pycache__" not in rel
        ):
            problems.append(f"unlisted {rel}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", type=Path, help="owner-only data root (default $SKYSYNTH_PRIVATE)")
    ap.add_argument(
        "--refit",
        type=Path,
        help="out-of-fold refit table (default <private>/refit/predictions_refit.json)",
    )
    ap.add_argument(
        "--check", action="store_true", help="compare seed/ against SEED_MANIFEST.json and exit"
    )
    args = ap.parse_args(argv)
    if args.check:
        problems = check()
        for p in problems:
            print(p)
        print(
            "seed matches SEED_MANIFEST.json" if not problems else f"{len(problems)} difference(s)"
        )
        return 1 if problems else 0

    private = _private_root(args.private)
    traces = private / "build" / "llm-router" / "evaluator" / "benchmark" / ".data" / "traces"
    train = traces / "trace_merged_train.jsonl"
    if not train.is_file():
        raise SystemExit(f"missing {train}; run tools/prepare_data.py traces first")
    refit_path = args.refit or private / "refit" / "predictions_refit.json"
    if not refit_path.is_file():
        raise SystemExit(
            f"missing {refit_path}; run tools/refit_predictions_oof.py first (the study's seed carries "
            "out-of-fold train predictions, never upstream's in-sample table)"
        )
    refit = json.loads(refit_path.read_text())
    for req in (UPSTREAM / "task.md", UPSTREAM / "LICENSE"):
        if not req.is_file():
            raise SystemExit(f"missing {req}; run tools/prepare_data.py vendor first")

    previous = (
        json.loads((SEED / "SEED_MANIFEST.json").read_text())
        if (SEED / "SEED_MANIFEST.json").is_file()
        else None
    )
    if SEED.exists():
        shutil.rmtree(SEED)
    (SEED / "evaluator").mkdir(parents=True)
    (SEED / "task" / "cards").mkdir(parents=True)
    (SEED / "data").mkdir()
    (SEED / "tools" / "upstream_replay" / "evaluator" / "benchmark").mkdir(parents=True)

    (SEED / "README.md").write_text(README)
    (SEED / "solution.py").write_text(REFERENCE_SOLUTION)
    (SEED / "evaluator" / "__init__.py").write_text("")
    shutil.copy2(
        GRADER_SRC / "public_router_interface.py", SEED / "evaluator" / "router_interface.py"
    )

    bench = UPSTREAM / "evaluator" / "benchmark"
    shutil.copy2(UPSTREAM / "task.md", SEED / "task" / "task.md")
    shutil.copy2(bench / "env_card.yaml", SEED / "task" / "env_card.yaml")
    shutil.copy2(bench / "data" / "fleet_flagship.json", SEED / "task" / "fleet_flagship.json")
    for card in (bench / "data" / "cards").glob("*.yaml"):
        shutil.copy2(card, SEED / "task" / "cards" / card.name)
    shutil.copy2(UPSTREAM / "evaluator" / "generic_policy.py", SEED / "task" / "generic_policy.py")
    shutil.copy2(
        UPSTREAM / "evaluator" / "reference_router.py", SEED / "task" / "reference_router.py"
    )
    shutil.copy2(UPSTREAM / "LICENSE", SEED / "task" / "LICENSE.upstream")

    # Public replay: upstream's two replay modules, unmodified, plus the tool.
    up = SEED / "tools" / "upstream_replay" / "evaluator"
    (up / "__init__.py").write_text("")
    (up / "benchmark" / "__init__.py").write_text("")
    for name in ("replay.py", "replay_tenants.py"):
        shutil.copy2(bench / name, up / "benchmark" / name)
    # replay.py imports evaluator.router_interface from the tree it sits in;
    # give it the public interface so the local replay's Request matches.
    shutil.copy2(GRADER_SRC / "public_router_interface.py", up / "router_interface.py")
    (SEED / "tools" / "replay_pair.py").write_text(REPLAY_TOOL)

    # Training data: the train trace verbatim (labels are training data) and
    # the OUT-OF-FOLD prediction table restricted to train prompt ids.
    shutil.copy2(train, SEED / "data" / "trace_merged_train.jsonl")
    train_ids = {json.loads(line)["features"]["prompt_id"] for line in open(train)}
    art = json.loads((bench / "artifacts" / "generic_predictions.json").read_text())
    oof_all = refit["pred"]["train_oof"]
    if not train_ids <= set(oof_all):
        raise SystemExit("refusing: the refit table does not cover every train prompt id")
    restricted = {
        "meta": {
            **art["meta"],
            "restricted_to": "train prompt_ids only; val/test predictions are attached per request by the trusted runtime",
            "predicts": "train prompt_ids, OUT OF FOLD (5-fold refit of the same recipe)",
            "out_of_fold": True,
            "folds_seed": refit["meta"]["folds_seed"],
        },
        "fleet": refit["fleet"],
        "mean_cost_train": art["mean_cost_train"],
        "pred": {k: oof_all[k] for k in sorted(train_ids)},
    }
    payload = json.dumps(restricted, sort_keys=True)
    (SEED / "data" / "predictions_train.json").write_text(payload)

    # Refuse to ship anything from val/test.
    for p in SEED.rglob("*"):
        if p.is_file() and any(tok in p.name for tok in ("_val", "_test", "bench-release")):
            raise SystemExit(f"refusing: seed would contain {p}")
    leaked = {k for k in restricted["pred"] if k not in train_ids}
    if leaked:
        raise SystemExit(
            f"refusing: predictions_train.json contains non-train ids: {sorted(leaked)[:3]}"
        )

    manifest = {
        f.relative_to(SEED).as_posix(): sha(f) for f in sorted(SEED.rglob("*")) if f.is_file()
    }
    (SEED / "SEED_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")

    # The owner-only copy the grader reads: train trace + the same OOF table.
    rp = private / "router_private"
    (rp / "traces").mkdir(parents=True, exist_ok=True)
    shutil.copy2(train, rp / "traces" / "trace_merged_train.jsonl")
    (rp / "predictions_train_oof.json").write_text(payload)
    (rp / "MANIFEST.json").write_text(
        json.dumps(
            {
                "contents": "TRAIN split only; val/test are never copied into any run directory",
                "files": {
                    "traces/trace_merged_train.jsonl": sha(train),
                    "predictions_train_oof.json": hashlib.sha256(payload.encode()).hexdigest(),
                },
                "rows": len(train_ids),
            },
            indent=1,
        )
        + "\n"
    )

    print(
        f"seed: {len(manifest)} files; train rows {len(train_ids)}; out-of-fold predictions {len(restricted['pred'])}"
    )
    print(f"router_private: {rp}")
    if previous is not None:
        changed = sorted(
            k for k in set(previous) | set(manifest) if previous.get(k) != manifest.get(k)
        )
        if changed:
            print(
                "files differing from the previous SEED_MANIFEST.json (the out-of-fold table is a float "
                f"refit and may differ across machines; everything else should not): {changed}"
            )
        else:
            print("seed is byte-identical to the previous SEED_MANIFEST.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
