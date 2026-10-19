#!/usr/bin/env python3
"""Discrete-event replay of a trace through a Router against the mock fleet.

The harness owns the clock, billing, and every invariant in task.md; routers only place requests.

    python replay.py TRACE.jsonl evaluator.reference_router.ReferenceRouter [--env env_card.yaml] [--json]
"""

import argparse
import copy
import heapq
import importlib
import json
import os
import random
import sys
import time
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from evaluator.router_interface import Action, Request  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

# The router gets a copy of each request; the harness scores from its own record and reports any
# edit to the copy as req_mutation.
REQ_FIELDS = tuple(Request.__dataclass_fields__)

# Liveness budgets, far above any honest replay, so a livelocked router aborts with a typed
# harness_hang violation instead of hanging the test.
DEFAULT_MAX_WALL_MS = 600_000  # real seconds, not simulated ones
DEFAULT_DECIDES_PER_REQ = 512  # global budget = this x len(trace)
_WALL_CHECK_EVERY = 256  # decide() calls between clock reads

# Defers allowed on a request no provider could ever serve before it counts as lost. The fleet view
# shows current headroom, not standing capacity, so a router is entitled to a few looks.
UNSERVICEABLE_DEFER_GRACE = 32


_MISSING = object()


def _copy_val(v):
    return list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v


def _clone_req(r):
    """Router-facing copy: new object, new list/dict containers, same values."""
    return type(r)(**{k: _copy_val(v) for k, v in r.__dict__.items()})


class Provider:
    def __init__(self, name, cfg, rng, retry_after_ms):
        self.name = name
        # private snapshot: capacity limits and the price table used for billing are
        # never the same objects the fleet view publishes to the router
        self.cfg = copy.deepcopy(cfg)
        self.rng = rng
        self.retry_after_ms = retry_after_ms
        self.inflight = 0
        self.req_window = deque()  # dispatch times (ms) in the last 60 s
        self.tok_window = deque()  # (ms, tokens)
        self.tok_sum = 0
        self.cache = {}  # prefix_id -> last-use ms (LRU)
        self.cache_ver = 0  # bumped on every cache mutation (snapshot memo)
        self._cache_snap = (-1, frozenset())
        self.stats = {
            "dispatches": 0,
            "throttles_429": 0,
            "errors_503": 0,
            "cache_hit_tokens": 0,
            "billed_usd": 0.0,
        }

    def _prune(self, now):
        cut = now - 60_000
        while self.req_window and self.req_window[0] <= cut:
            self.req_window.popleft()
        while self.tok_window and self.tok_window[0][0] <= cut:
            self.tok_sum -= self.tok_window.popleft()[1]

    def admit(self, req, model, now):
        """Returns ("ok", ttft_ms, total_ms, cost_usd, cached_tokens) or ("429"/"503", retry_after)."""
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

        # A warm prefix discounts at most the whole prompt; the fresh-token term can never become a credit.
        cached = min(req.prefix_tokens, req.prompt_tokens) if req.prefix_id in self.cache else 0
        self.stats["cache_hit_tokens"] += cached
        self.cache[req.prefix_id] = now
        if len(self.cache) > self.cfg.get("cache_entries", 500):
            self.cache.pop(min(self.cache, key=self.cache.get))
        self.cache_ver += 1

        fresh = req.prompt_tokens - cached
        prefill_ms = fresh / self.cfg["prefill_tps"] * 1000
        prefill_ms += cached / (self.cfg["prefill_tps"] * self.cfg.get("cache_speedup", 8)) * 1000
        ttft = self.cfg["ttft_base_ms"] + prefill_ms
        total = ttft + req.expected_output_tokens / self.cfg["decode_tps"] * 1000

        p = self.cfg["models"][model]
        cost = (
            fresh * p["in"] + cached * p["cached"] + req.expected_output_tokens * p["out"]
        ) / 1e6
        self.stats["billed_usd"] += cost
        return ("ok", ttft, total, cost, cached)


class Replay:
    def __init__(self, env_path):
        # no-yaml interpreters use a pre-converted sibling .json of the env card
        if yaml is None and env_path.endswith((".yaml", ".yml")):
            sibling = os.path.splitext(env_path)[0] + ".json"
            if os.path.exists(sibling):
                env_path = sibling
        with open(env_path) as f:
            self.env = yaml.safe_load(f) if yaml else json.load(f)
        self.rng = random.Random(self.env.get("sim_seed", 11))
        self.providers = {
            name: Provider(name, cfg, self.rng, self.env["retry_after_ms"])
            for name, cfg in self.env["providers"].items()
        }
        self._env_fp0 = self._env_fingerprint()

    def _env_fingerprint(self):
        """Tripwire over the fleet truth (prices, capacity) as loaded from the env card.
        Nothing published to a router aliases it, so this must be unchanged at end of
        run; a delta means some path started leaking the fleet's own tables again."""
        return json.dumps(
            [self.env["providers"], {n: p.cfg for n, p in self.providers.items()}], sort_keys=True
        )

    def _warm_prefixes(self, p):
        """Immutable snapshot of a provider's warm-prefix keys, memoised on the cache
        version so a defer loop does not rebuild it per decide."""
        ver, snap = p._cache_snap
        if ver != p.cache_ver:
            snap = frozenset(p.cache)
            p._cache_snap = (p.cache_ver, snap)
        return snap

    def _ever_servable(self, req):
        """Could any provider ever admit this request on an empty fleet? Structural capacity only, read as
        widely as possible, so a request that fails this cannot become servable by waiting.
        """
        models = set(req.equiv_class or ()) | {req.model_requested}
        tokens = req.prompt_tokens + req.expected_output_tokens
        for p in self.providers.values():
            cfg = p.cfg
            if (
                models & set(cfg["models"])
                and tokens <= cfg["tpm"]
                and cfg["rpm"] >= 1
                and cfg["concurrency"] >= 1
            ):
                return True
        return False

    def fleet_view(self):
        view = {}
        for name, p in self.providers.items():
            p._prune(getattr(self, "_now", 0))
            view[name] = {
                # read-only truth, published by value: a router that edits the price
                # table or the headroom counters edits its own copy and bills unchanged
                "models": {m: dict(price) for m, price in p.cfg["models"].items()},
                "inflight": p.inflight,
                "rpm_left": p.cfg["rpm"] - len(p.req_window),
                "tpm_left": p.cfg["tpm"] - p.tok_sum,
                "error_rate": p.cfg.get("error_rate", 0.0),
                # Closes over a snapshot, never the Provider, so the router cannot reach the billing meter.
                "has_prefix": (lambda pid, _w=self._warm_prefixes(p): pid in _w),
            }
        return view

    def run(self, trace_path, router, max_wall_ms=None, max_decides=None):
        # reqs is harness truth and is never handed to the router. Accounting is keyed by row index, not
        # req_id: ids are caller-supplied and may repeat (the id-reuse probe).
        reqs = [Request.from_json(json.loads(l)) for l in open(trace_path)]
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

        # Independent tally of what the score is read from; a divergence from the provider's own total is
        # reported as meter_mutation at run end.
        billed_own = {name: 0.0 for name in self.providers}

        decides = 0
        if max_decides is None:
            max_decides = DEFAULT_DECIDES_PER_REQ * max(len(reqs), 1)
        wall_budget = DEFAULT_MAX_WALL_MS if max_wall_ms is None else max_wall_ms
        t_start = time.monotonic()
        aborted = None

        def facing(i):
            """The router-facing copy of row i, stable identity across decide/on_error/
            on_complete so a router may key on it, but never the harness's record."""
            p = proxies.get(i)
            if p is None:
                p = proxies[i] = _clone_req(reqs[i])
            return p

        def guard(i):
            """Diff the router-facing copy against truth after a callback. Any edit to a
            trace field is reported once as req_mutation and rolled back; extra scratch
            attributes a router hangs on its own copy are its business and are ignored."""
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
            """Call the router; an exception becomes a typed router_exception attributed to the router and the
            replay finishes its accounting.
            """
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
                # Shed is legal only under overload: no provider serving a legally substitutable model (the requested
                # model, plus the equivalence class only when downgradeable) has headroom right now.
                servable = (
                    {req.model_requested} | set(req.equiv_class)
                    if req.downgrade_ok
                    else {req.model_requested}
                )
                for pname, prov in self.providers.items():
                    if not any(m in prov.cfg["models"] for m in servable):
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
                proxies.pop(i, None)
                return
            if action.kind == "defer":
                # Deferring a request no provider could ever admit is losing it slowly; past the grace window report
                # it against the router (shed is the legal way out).
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
                # wakes beyond the horizon are dropped: a router deferring past end-of-trace
                # has lost the request, and the end-of-run check will flag it
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
            res = prov.admit(req, model, now)
            if res[0] in ("429", "503"):
                call_router("on_error", i, router.on_error, now, res[0], res[1])
                guard(i)
                heapq.heappush(events, (now + res[1], 1, seq, "wake", i))
                seq += 1
                return
            _, ttft, total, cost, _cached = res
            billed_own[prov.name] += cost
            # Meter invariant: a prefix hit discounts down to the cached rate and no further, so the bill is never
            # below the all-cached price and never a credit.
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
            heapq.heappush(
                events, (now + int(total), 2, seq, "complete", (i, prov, cost, ttft, model))
            )
            seq += 1

        while events:
            now, _, _, kind, payload = heapq.heappop(events)
            self._now = now
            if kind in ("arrive", "wake"):
                i = payload
                if state[i]["completions"] or state[i]["shed"] or state[i]["dead"]:
                    continue
                # liveness: a livelocked router must fail LOUDLY and quickly, never grind
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
                i, prov, cost, ttft, model = payload
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
                # latency vs SLO: whole-response for latency_ms, arrival→first-token for ttft_ms
                if "latency_ms" in req.slo:
                    measured = now - req.t_ms
                    limit = req.slo["latency_ms"]
                else:
                    measured = (now - req.t_ms) - req.expected_output_tokens / prov.cfg[
                        "decode_tps"
                    ] * 1000
                    limit = req.slo["ttft_ms"]
                lat[bucket].append(measured)
                if measured > limit:
                    slo_viol[bucket] += 1
                cost_by_class[req.cls] = cost_by_class.get(req.cls, 0.0) + cost
                action = call_router("on_complete", i, router.on_complete, now)
                guard(i)
                proxies.pop(i, None)
                handle(action, i, now)

        if aborted:
            violations.append(("harness_hang", None, aborted))
        for i, st in state.items():
            # dead rows already carry the more specific unserviceable violation
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

        # A shed request scores zero quality and a floor miss; averaging over completions only would make
        # refusing work the cheapest way to improve every axis.
        shed_n = sum(1 for st in state.values() if st["shed"])
        quality_n += shed_n
        floor_misses += shed_n

        def p95(xs):
            xs = sorted(xs)
            return round(xs[int(0.95 * (len(xs) - 1))], 1) if xs else None

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
                sum(p.stats["cache_hit_tokens"] for p in self.providers.values()) / total_prompt, 3
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
        }


def load_router(path):
    mod, cls = path.rsplit(".", 1)
    return getattr(importlib.import_module(mod), cls)()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("router_class")
    ap.add_argument(
        "--env", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "env_card.yaml")
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-wall-ms", type=float, default=None)
    ap.add_argument("--max-decides", type=int, default=None)
    args = ap.parse_args()
    result = Replay(args.env).run(
        args.trace,
        load_router(args.router_class),
        max_wall_ms=args.max_wall_ms,
        max_decides=args.max_decides,
    )
    print(json.dumps(result, indent=None if args.json else 2))


if __name__ == "__main__":
    main()
