#!/usr/bin/env python3
"""Owner-side infrastructure check: reproduce the shipped generic validation numbers.

    python tools/reproduce_generic_baseline.py --val-trace <private>/trace_merged_val.jsonl

Replays upstream's registered ``GenericPolicy(lam=40, placement="latency")``
in-process on merged validation with the val outage windows and compares every
saved field in ``generic_baseline_results.json`` (merged and per tenant). Exits
non-zero on any mismatch. This is a reproduction of a fixed baseline, not
permission to tune anything on validation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TASK = Path(__file__).resolve().parents[1]
UPSTREAM = TASK / "upstream"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--val-trace", type=Path, required=True)
    args = ap.parse_args(argv)
    if "_val." not in args.val_trace.name:
        raise SystemExit("refusing: this reproduces the VALIDATION baseline only")
    sys.path.insert(0, str(UPSTREAM))
    from evaluator.benchmark.replay_tenants import TenantReplay
    from evaluator.generic_policy import GenericPolicy

    card = UPSTREAM / "evaluator" / "benchmark" / "env_card.yaml"
    res = TenantReplay(str(card), split="val").run(str(args.val_trace), GenericPolicy())
    saved = json.loads(
        (UPSTREAM / "evaluator/benchmark/baseline/generic_baseline_results.json").read_text()
    )
    n = res["requests"]
    viol = sum(res["slo_violations"].values())
    lost = n - res["completed"] - res["shed"]
    rate = (viol + res["shed"] + lost) / n
    u = res["mean_quality"] - rate - 3.0 * res["total_cost_usd"] / n
    sm = saved["val"]["merged"]
    rows = [
        ("mean_quality", res["mean_quality"], sm["mean_quality"]),
        ("total_cost_usd", res["total_cost_usd"], sm["total_cost_usd"]),
        ("slo_violation_rate", round(rate, 4), sm["slo_violation_rate"]),
        ("violation_count", res["violation_count"], sm["violation_count"]),
        ("utility", round(u, 4), saved["selected"]["utility"]),
    ]
    bad = 0
    print(f"{'field':22}{'reproduced':>12}{'saved':>12}")
    for k, a, b in rows:
        ok = a == b
        bad += not ok
        print(f"{k:22}{a!s:>12}{b!s:>12}  {'ok' if ok else 'MISMATCH'}")
    for t in ("A", "B"):
        r, s = res["tenants"][t], saved["val"]["per_tenant"][t]
        diffs = {k: (r.get(k), s[k]) for k in s if r.get(k) != s[k]}
        bad += bool(diffs)
        print(
            f"tenant {t}: {'all fields identical' if not diffs else 'MISMATCH ' + json.dumps(diffs)}"
        )
    print("generic validation baseline", "REPRODUCED" if not bad else "NOT reproduced")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
