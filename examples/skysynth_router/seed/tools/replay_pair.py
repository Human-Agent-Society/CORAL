#!/usr/bin/env python3
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
        trace.write_text("".join(json.dumps(r) + "\n" for r in c["requests"]))
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
