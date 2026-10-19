"""The generic baseline policy: one tenant-blind policy for the merged traffic (task.md).

Picks the model by argmax pred_score - lambda * mean_cost from a precomputed prediction
artifact, then places it on the cheapest provider with headroom (optionally the cheapest that
fits the TTFT budget), backing off on 429/503/outage. Reads only the request's public fields.
lambda and the placement variant come from evaluator/benchmark/baseline/train_generic.py.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from evaluator.router_interface import Action, Router  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

DEFAULT_PRED = os.path.join(HERE, "evaluator", "benchmark", "artifacts", "generic_predictions.json")
DEFAULT_CARD = os.path.join(HERE, "evaluator", "benchmark", "env_card.yaml")


class GenericPolicy(Router):
    # The zero-argument construction is the registered baseline: lam=40 under the
    # "latency" placement is the operating point the logged 5-evaluation tuning selected
    # (evaluator/benchmark/baseline/generic_baseline_results.json), and the replay CLI builds routers with
    # zero arguments, so the bar-to-beat must be constructible that way.
    def __init__(
        self,
        lam=40.0,
        placement="latency",
        predictions_path=DEFAULT_PRED,
        env_card_path=DEFAULT_CARD,
        headroom_rpm=2,
        ttft_budget_frac=0.8,
    ):
        art = json.load(open(predictions_path))
        self.fleet = art["fleet"]
        self.pred = art["pred"]  # prompt_id -> [score per fleet model]
        self.mean_cost = art["mean_cost_train"]  # model -> train-mean measured cost
        self.lam = float(lam)
        self.placement = placement
        self.headroom_rpm = headroom_rpm
        self.ttft_budget_frac = ttft_budget_frac
        # static latency + concurrency spec from the frozen, public env card (never
        # mutated at run time; the live outage/headroom signal comes from the fleet view)
        card = yaml.safe_load(open(env_card_path))
        self.latency_spec = {
            name: (cfg["ttft_base_ms"], cfg["prefill_tps"])
            for name, cfg in card["providers"].items()
        }
        self.concurrency = {name: cfg["concurrency"] for name, cfg in card["providers"].items()}
        self.attempts = {}

    # model choice
    def choose_model(self, req):
        preds = self.pred.get((req.features or {}).get("prompt_id"))
        if preds is None:
            model = req.model_requested
        else:
            best, model = None, req.model_requested
            for j, m in enumerate(self.fleet):
                u = preds[j] - self.lam * self.mean_cost[m]
                if best is None or u > best:
                    best, model = u, m
        if model != req.model_requested and not (req.downgrade_ok and model in req.equiv_class):
            model = req.model_requested
        return model

    # placement
    def est_ttft_ms(self, provider, req):
        base, prefill = self.latency_spec.get(provider, (1000.0, 20000.0))
        return base + req.prompt_tokens / prefill * 1000.0

    def decide(self, req, now_ms, fleet_view):
        model = self.choose_model(req)
        serving = [(n, v) for n, v in fleet_view.items() if model in v["models"]]
        if not serving:
            # sole serving provider announced an outage (or the model is nowhere): wait
            return Action("defer", until_ms=now_ms + 1000)

        def price(v):
            p = v["models"][model]
            return req.prompt_tokens * p["in"] + req.expected_output_tokens * p["out"]

        ranked = sorted(serving, key=lambda nv: (price(nv[1]), nv[0]))
        if self.placement == "latency" and "ttft_ms" in req.slo:
            budget = self.ttft_budget_frac * req.slo["ttft_ms"]
            fast = [nv for nv in ranked if self.est_ttft_ms(nv[0], req) <= budget]
            ranked = fast or sorted(ranked, key=lambda nv: (self.est_ttft_ms(nv[0], req), nv[0]))

        tokens = req.prompt_tokens + req.expected_output_tokens
        for name, view in ranked:
            if (
                view["rpm_left"] > self.headroom_rpm
                and view["tpm_left"] >= tokens
                # concurrency is not published live; the card's standing limit is public
                # spec, and inflight is, dispatching into a full provider only buys a
                # 429 and a 2 s back-off, so spill to the next provider instead
                and view["inflight"] < self.concurrency.get(name, 10**9)
            ):
                return Action("dispatch", provider=name, model=model)
        # everything serving this model is saturated: back off (exponential, capped)
        k = self.attempts.get(req.req_id, 0)
        self.attempts[req.req_id] = k + 1
        return Action("defer", until_ms=now_ms + min(4000, 250 * (2 ** min(k, 4))))

    def on_error(self, req, now_ms, kind, retry_after_ms):
        self.attempts[req.req_id] = self.attempts.get(req.req_id, 0) + 1

    def on_complete(self, req, now_ms):
        self.attempts.pop(req.req_id, None)
        return None
