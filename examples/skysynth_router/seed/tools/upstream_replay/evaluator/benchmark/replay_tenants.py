#!/usr/bin/env python3
"""replay.py plus tenants: per-tenant reporting, scheduled provider outages, per-model latency.

A provider in outage publishes an empty catalogue and outage_until in the fleet view; a router
that keeps dispatching into it past retry_grace has lost the request (outage_lost). Val outage
windows are literal in the card; test windows are derived from the card's seed at replay time.

    python replay_tenants.py TRACE.jsonl RouterClassPath --env env_card.yaml [--split val|test|none] [--json]
"""

import argparse
import hashlib
import heapq
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from evaluator.benchmark.replay import (  # noqa: E402
    _MISSING,
    _WALL_CHECK_EVERY,
    DEFAULT_DECIDES_PER_REQ,
    DEFAULT_MAX_WALL_MS,
    REQ_FIELDS,
    UNSERVICEABLE_DEFER_GRACE,
    Provider,
    Replay,
    _clone_req,
    _copy_val,
    load_router,
)
from evaluator.router_interface import Request  # noqa: E402


def derive_test_outage_windows(seed, span_ms):
    """Two premium-outage windows for the SEALED test split, derived from the card's
    committed seed and the trace span. Deterministic and inspectable only by running it,
    which this round's tuning code never does (the harness owner replays test)."""
    windows = []
    for k in range(2):
        h1 = int(hashlib.sha256(f"round4-test-outage-{seed}-{k}-start".encode()).hexdigest(), 16)
        h2 = int(hashlib.sha256(f"round4-test-outage-{seed}-{k}-len".encode()).hexdigest(), 16)
        lo, hi = 0.10 + 0.45 * k, 0.35 + 0.45 * k
        start = (lo + (h1 % 10**6) / 10**6 * (hi - lo)) * span_ms
        length = (90.0 + (h2 % 10**6) / 10**6 * 120.0) * 1000.0  # 90-210 s
        windows.append((int(start), int(start + length)))
    return windows


class TenantProvider(Provider):
    """Provider with scheduled outages and per-model latency overrides; billing is unchanged."""

    def __init__(self, name, cfg, rng, retry_after_ms):
        super().__init__(name, cfg, rng, retry_after_ms)
        self.outage_windows = []  # [(start_ms, end_ms)] set by TenantReplay.run
        self.stats["outage_503"] = 0

    def down(self, now):
        return any(s <= now < e for s, e in self.outage_windows)

    def model_latency(self, model):
        """(decode_tps, ttft_extra_ms) for one model: per-model override or provider
        default. Reasoning models carry slower decode in the card."""
        entry = self.cfg["models"].get(model, {})
        return (
            float(entry.get("decode_tps", self.cfg["decode_tps"])),
            float(entry.get("ttft_extra_ms", 0.0)),
        )

    def admit(self, req, model, now):
        # ADDED: a down provider admits nothing; typed separately from a rate 429 so the
        # outage-blind accounting upstream can tell them apart.
        if self.down(now):
            self.stats["outage_503"] += 1
            return ("503", self.retry_after_ms)
        self._prune(now)
        tokens = req.prompt_tokens + req.expected_output_tokens
        if (
            model not in self.cfg["models"]
            or self.inflight >= self.cfg["concurrency"]
            or len(self.req_window) >= self.cfg["rpm"]
            or self.tok_sum + tokens > self.cfg["tpm"]
        ):
            self.stats["throttles_429"] += 1
            return ("429", self.retry_after_ms)
        if self.rng.random() < self.cfg.get("error_rate", 0.0):
            self.stats["errors_503"] += 1
            return ("503", self.retry_after_ms // 2)
        self.req_window.append(now)
        self.tok_window.append((now, tokens))
        self.tok_sum += tokens
        self.inflight += 1
        self.stats["dispatches"] += 1

        cached = min(req.prefix_tokens, req.prompt_tokens) if req.prefix_id in self.cache else 0
        self.stats["cache_hit_tokens"] += cached
        self.cache[req.prefix_id] = now
        if len(self.cache) > self.cfg.get("cache_entries", 500):
            self.cache.pop(min(self.cache, key=self.cache.get))
        self.cache_ver += 1

        fresh = req.prompt_tokens - cached
        prefill_ms = fresh / self.cfg["prefill_tps"] * 1000
        prefill_ms += cached / (self.cfg["prefill_tps"] * self.cfg.get("cache_speedup", 8)) * 1000
        decode_tps, ttft_extra = self.model_latency(model)  # ADDED
        ttft = self.cfg["ttft_base_ms"] + ttft_extra + prefill_ms
        total = ttft + req.expected_output_tokens / decode_tps * 1000

        p = self.cfg["models"][model]
        cost = (
            fresh * p["in"] + cached * p["cached"] + req.expected_output_tokens * p["out"]
        ) / 1e6
        self.stats["billed_usd"] += cost
        return ("ok", ttft, total, cost, cached)


class TenantReplay(Replay):
    def __init__(self, env_path, split="val"):
        super().__init__(env_path)
        self.split = None if split in (None, "none") else split
        oc = self.env.get("outages") or {}
        self.outage_provider = oc.get("provider")
        self.outage_grace = int(oc.get("retry_grace", 8))
        # tenant-world providers (same cfg, same rng): outages + per-model latency
        self.providers = {
            name: TenantProvider(name, cfg, self.rng, self.env["retry_after_ms"])
            for name, cfg in self.env["providers"].items()
        }
        self._env_fp0 = self._env_fingerprint()

    def _resolve_outages(self, span_ms):
        oc = self.env.get("outages") or {}
        if not oc or self.outage_provider not in self.providers or self.split is None:
            return []
        if self.split == "test":
            return derive_test_outage_windows(oc["test_seed"], span_ms)
        return [(int(s), int(e)) for s, e in oc.get(self.split, [])]

    def fleet_view(self):
        now = getattr(self, "_now", 0)
        view = {}
        for name, p in self.providers.items():
            p._prune(now)
            if p.down(now):  # ADDED: announced outage, empty catalogue, ETA published
                view[name] = {
                    "models": {},
                    "inflight": p.inflight,
                    "rpm_left": 0,
                    "tpm_left": 0,
                    "error_rate": p.cfg.get("error_rate", 0.0),
                    "outage_until": next(e for s, e in p.outage_windows if s <= now < e),
                    "has_prefix": (lambda pid, _w=self._warm_prefixes(p): pid in _w),
                }
                continue
            view[name] = {
                "models": {m: dict(price) for m, price in p.cfg["models"].items()},
                "inflight": p.inflight,
                "rpm_left": p.cfg["rpm"] - len(p.req_window),
                "tpm_left": p.cfg["tpm"] - p.tok_sum,
                "error_rate": p.cfg.get("error_rate", 0.0),
                "has_prefix": (lambda pid, _w=self._warm_prefixes(p): pid in _w),
            }
        return view

    # the run loop
    # A faithful copy of Replay.run with the additions marked "# ADDED:". Every floor
    # invariant, liveness budget and violation type of the base loop is preserved.
    def run(self, trace_path, router, max_wall_ms=None, max_decides=None):
        raw = [json.loads(l) for l in open(trace_path)]
        reqs = [Request.from_json(d) for d in raw]
        tenants = [d.get("tenant", "-") for d in raw]  # ADDED: harness-side tenant tag
        span_ms = (reqs[-1].t_ms if reqs else 0) + 1
        windows = self._resolve_outages(span_ms)  # ADDED
        for p in self.providers.values():
            p.outage_windows = windows if p.name == self.outage_provider else []

        events = [(r.t_ms, 0, i, "arrive", i) for i, r in enumerate(reqs)]
        heapq.heapify(events)
        seq = len(events)
        state = {
            i: {
                "bills": 0,
                "completions": 0,
                "shed": False,
                "dead": False,
                "dead_defers": 0,
                "outage_rejects": 0,  # ADDED
                "req": r,
            }
            for i, r in enumerate(reqs)
        }
        violations = []
        lat = {"critical": [], "tolerant": []}
        slo_viol = {"critical": 0, "tolerant": 0}
        cost_by_class = {}
        quality_sum, quality_n, floor_misses = 0.0, 0, 0
        proxies, mutated = {}, set()

        # ADDED: per-tenant books (quality/cost/SLO/throttles), read from harness truth only
        tset = sorted(set(tenants))
        ten = {
            t: {
                "requests": 0,
                "completed": 0,
                "shed": 0,
                "quality_sum": 0.0,
                "quality_n": 0,
                "cost_usd": 0.0,
                "slo_violations": 0,
                "throttles_429": 0,
                "outage_rejects": 0,
                "lat": [],
            }
            for t in tset
        }
        for t in tenants:
            ten[t]["requests"] += 1

        billed_own = {name: 0.0 for name in self.providers}

        decides = 0
        if max_decides is None:
            max_decides = DEFAULT_DECIDES_PER_REQ * max(len(reqs), 1)
        wall_budget = DEFAULT_MAX_WALL_MS if max_wall_ms is None else max_wall_ms
        t_start = time.monotonic()
        aborted = None

        def facing(i):
            p = proxies.get(i)
            if p is None:
                p = proxies[i] = _clone_req(reqs[i])
            return p

        def guard(i):
            req = reqs[i]
            p = proxies[i]
            diff = [f for f in REQ_FIELDS if getattr(p, f, _MISSING) != getattr(req, f)]
            if not diff:
                return
            if i not in mutated:
                mutated.add(i)
                violations.append(("req_mutation", req.req_id, ",".join(diff)))
            for f in diff:
                setattr(p, f, _copy_val(getattr(req, f)))

        def call_router(what, i, fn, *args):
            try:
                return fn(facing(i), *args)
            except Exception as exc:  # not BaseException: Ctrl-C is ours
                violations.append(
                    (
                        "router_exception",
                        reqs[i].req_id,
                        f"{what}() raised {type(exc).__name__}: {str(exc)[:120]}",
                    )
                )
                return None

        def handle(action, i, now):
            nonlocal seq
            req = reqs[i]
            if action is None:
                return
            if action.kind == "shed":
                servable = (
                    {req.model_requested} | set(req.equiv_class)
                    if req.downgrade_ok
                    else {req.model_requested}
                )
                for pname, prov in self.providers.items():
                    if not any(m in prov.cfg["models"] for m in servable):
                        continue
                    if prov.down(now):  # ADDED: a down provider is not admission headroom
                        continue
                    prov._prune(now)
                    if (
                        prov.inflight < prov.cfg["concurrency"]
                        and len(prov.req_window) < prov.cfg["rpm"]
                        and prov.tok_sum + req.prompt_tokens + req.expected_output_tokens
                        <= prov.cfg["tpm"]
                    ):
                        violations.append(("illegal_shed", req.req_id, pname))
                        break
                state[i]["shed"] = True
                ten[tenants[i]]["shed"] += 1  # ADDED
                proxies.pop(i, None)
                return
            if action.kind == "defer":
                if not self._ever_servable(req):
                    state[i]["dead_defers"] += 1
                    if state[i]["dead_defers"] > UNSERVICEABLE_DEFER_GRACE:
                        state[i]["dead"] = True
                        violations.append(
                            (
                                "unserviceable",
                                req.req_id,
                                f"deferred {state[i]['dead_defers']} times, but no provider "
                                f"can ever serve {req.model_requested}/{req.equiv_class} at "
                                f"{req.prompt_tokens + req.expected_output_tokens} tokens",
                            )
                        )
                        proxies.pop(i, None)
                        return
                until = max(now + 1, action.until_ms or now + 1000)
                if until <= (reqs[-1].t_ms + 3_600_000):
                    heapq.heappush(events, (until, 1, seq, "wake", i))
                    seq += 1
                return
            # dispatch
            model = action.model or req.model_requested
            if model != req.model_requested and (
                not req.downgrade_ok or model not in req.equiv_class
            ):
                violations.append(("substitution", req.req_id, model))
            prov = self.providers.get(action.provider)
            if prov is None:
                violations.append(("unknown_provider", req.req_id, action.provider))
                return
            if model not in prov.cfg["models"]:
                violations.append(("unknown_model", req.req_id, f"{action.provider}:{model}"))
                return
            was_down = prov.down(now)  # ADDED
            res = prov.admit(req, model, now)
            if res[0] in ("429", "503"):
                # ADDED: outage-blind accounting. The view announced this outage (empty
                # catalogue + outage_until); a router that keeps dispatching into it past
                # the grace is losing the request in slow motion, exactly like the
                # unserviceable-defer treadmill, and is reported the same way.
                if was_down:
                    state[i]["outage_rejects"] += 1
                    ten[tenants[i]]["outage_rejects"] += 1
                    if state[i]["outage_rejects"] > self.outage_grace:
                        state[i]["dead"] = True
                        violations.append(
                            (
                                "outage_lost",
                                req.req_id,
                                f"dispatched to {prov.name} {state[i]['outage_rejects']} times "
                                f"during its announced outage window",
                            )
                        )
                        proxies.pop(i, None)
                        return
                elif res[0] == "429":
                    ten[tenants[i]]["throttles_429"] += 1  # ADDED
                call_router("on_error", i, router.on_error, now, res[0], res[1])
                guard(i)
                heapq.heappush(events, (now + res[1], 1, seq, "wake", i))
                seq += 1
                return
            _, ttft, total, cost, _cached = res
            billed_own[prov.name] += cost
            price = prov.cfg["models"][model]
            floor = (
                req.prompt_tokens * min(price["in"], price["cached"])
                + req.expected_output_tokens * price["out"]
            ) / 1e6
            if cost < 0 or cost + 1e-12 < floor:
                violations.append(
                    (
                        "bad_bill",
                        req.req_id,
                        f"{model}@{prov.name} billed {cost:.9f} " f"< all-cached floor {floor:.9f}",
                    )
                )
            # ADDED: the completion event carries the dispatch time so TTFT is measured
            # directly (dispatch + ttft - arrival) instead of backed out of a uniform
            # provider decode rate, which per-model decode makes wrong.
            heapq.heappush(
                events, (now + int(total), 2, seq, "complete", (i, prov, cost, ttft, model, now))
            )
            seq += 1

        while events:
            now, _, _, kind, payload = heapq.heappop(events)
            self._now = now
            if kind in ("arrive", "wake"):
                i = payload
                if state[i]["completions"] or state[i]["shed"] or state[i]["dead"]:
                    continue
                if decides >= max_decides:
                    aborted = (
                        f"decide() budget exhausted after {decides} calls "
                        f"(limit {max_decides} = {DEFAULT_DECIDES_PER_REQ}/request "
                        f"by default); the router is not making progress"
                    )
                    break
                if decides % _WALL_CHECK_EVERY == 0:
                    spent = (time.monotonic() - t_start) * 1000
                    if spent > wall_budget:
                        aborted = (
                            f"wall-clock budget exceeded: {spent:.0f} ms of real "
                            f"time (limit {wall_budget:.0f} ms) after {decides} "
                            f"decide() calls"
                        )
                        break
                decides += 1
                action = call_router("decide", i, router.decide, now, self.fleet_view())
                guard(i)
                handle(action, i, now)
            elif kind == "complete":
                i, prov, cost, ttft, model, t_dispatch = payload
                req = reqs[i]
                prov.inflight -= 1
                st = state[i]
                st["bills"] += 1
                st["completions"] += 1
                if st["bills"] > 1:
                    violations.append(("double_bill", req.req_id, prov.name))
                    continue
                q = (
                    req.quality.get(model, req.quality.get(req.model_requested, 1.0))
                    if req.quality
                    else 1.0
                )
                quality_sum += q
                quality_n += 1
                if q < req.quality_floor:
                    floor_misses += 1
                bucket = "tolerant" if req.downgrade_ok else "critical"
                if "latency_ms" in req.slo:
                    measured = now - req.t_ms
                    limit = req.slo["latency_ms"]
                else:
                    measured = (t_dispatch + ttft) - req.t_ms  # ADDED: direct TTFT
                    limit = req.slo["ttft_ms"]
                lat[bucket].append(measured)
                if measured > limit:
                    slo_viol[bucket] += 1
                cost_by_class[req.cls] = cost_by_class.get(req.cls, 0.0) + cost
                # ADDED: tenant books
                tb = ten[tenants[i]]
                tb["completed"] += 1
                tb["quality_sum"] += q
                tb["quality_n"] += 1
                tb["cost_usd"] += cost
                tb["lat"].append(measured)
                if measured > limit:
                    tb["slo_violations"] += 1
                action = call_router("on_complete", i, router.on_complete, now)
                guard(i)
                proxies.pop(i, None)
                handle(action, i, now)

        if aborted:
            violations.append(("harness_hang", None, aborted))
        for i, st in state.items():
            # dead rows already carry their specific violation (unserviceable /
            # outage_lost)
            if not st["completions"] and not st["shed"] and not st["dead"]:
                violations.append(("lost_request", st["req"].req_id, None))
        if self._env_fingerprint() != self._env_fp0:
            violations.append(("env_mutation", None, "fleet config changed during the run"))
        for name, prov in self.providers.items():
            if abs(prov.stats["billed_usd"] - billed_own[name]) > 1e-9:
                violations.append(
                    (
                        "meter_mutation",
                        None,
                        f"{name}.stats billed {prov.stats['billed_usd']:.9f} != harness "
                        f"ledger {billed_own[name]:.9f}",
                    )
                )

        # shed scores zero quality and misses its floor (replay.py rule)
        shed_n = sum(1 for st in state.values() if st["shed"])
        quality_n += shed_n
        floor_misses += shed_n

        def p95(xs):
            xs = sorted(xs)
            return round(xs[int(0.95 * (len(xs) - 1))], 1) if xs else None

        # ADDED: close each tenant's books. SLO-violation RATE counts a non-answer (shed,
        # lost, dead) as a violated request: a request that never completed certainly did
        # not meet its SLO, and a rate over completions only would pay a router to drop
        # its hardest traffic.
        tenants_out = {}
        for t in tset:
            tb = ten[t]
            lost = tb["requests"] - tb["completed"] - tb["shed"]
            qn = tb["quality_n"] + tb["shed"]  # shed scores zero, as in the global books
            tenants_out[t] = {
                "requests": tb["requests"],
                "completed": tb["completed"],
                "shed": tb["shed"],
                "lost_or_dead": lost,
                "mean_quality": round(tb["quality_sum"] / qn, 4) if qn else None,
                "cost_usd": round(tb["cost_usd"], 4),
                "slo_violations": tb["slo_violations"],
                "slo_violation_rate": (
                    round((tb["slo_violations"] + tb["shed"] + lost) / tb["requests"], 4)
                    if tb["requests"]
                    else None
                ),
                "throttles_429": tb["throttles_429"],
                "outage_rejects": tb["outage_rejects"],
                "p95_latency_ms": p95(tb["lat"]),
            }

        total_prompt = sum(r.prompt_tokens for r in reqs)
        return {
            "trace": os.path.basename(trace_path),
            "router": type(router).__name__,
            "requests": len(reqs),
            "total_cost_usd": round(sum(billed_own.values()), 4),
            "cost_by_class_usd": {k: round(v, 4) for k, v in sorted(cost_by_class.items())},
            "slo_violations": slo_viol,
            "mean_quality": round(quality_sum / quality_n, 4) if quality_n else None,
            "quality_floor_misses": floor_misses,
            "shed": shed_n,
            "completed": sum(1 for s in state.values() if s["completions"]),
            "decides": decides,
            "aborted": aborted,
            "p95_latency_ms": {k: p95(v) for k, v in lat.items()},
            "prefix_cache_hit_token_fraction": round(
                sum(p.stats["cache_hit_tokens"] for p in self.providers.values())
                / max(total_prompt, 1),
                3,
            ),
            "violations": violations[:20],
            "violation_count": len(violations),
            "violation_kinds": dict(
                sorted(__import__("collections").Counter(v[0] for v in violations).items())
            ),
            "leading_indicators": {
                name: dict(p.stats, billed_usd=round(billed_own[name], 4))
                for name, p in self.providers.items()
            },
            # ADDED: tenant-world additions
            "split": self.split,
            "outage_windows_ms": windows,
            "tenants": tenants_out,
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("router_class")
    ap.add_argument(
        "--env",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "env_card.yaml"),
    )
    ap.add_argument("--split", default="val", choices=["val", "test", "none"])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-wall-ms", type=float, default=None)
    ap.add_argument("--max-decides", type=int, default=None)
    args = ap.parse_args()
    result = TenantReplay(args.env, split=args.split).run(
        args.trace,
        load_router(args.router_class),
        max_wall_ms=args.max_wall_ms,
        max_decides=args.max_decides,
    )
    print(json.dumps(result, indent=None if args.json else 2))


if __name__ == "__main__":
    main()
