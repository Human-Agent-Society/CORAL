"""Trusted-correct baseline: requested model, first provider that serves it, retry via
harness wake-ups, never sheds, no affinity, no pacing. Slow and expensive on purpose,
this is the PASS oracle every test is validated against, and the number to beat."""

from evaluator.router_interface import Action, Router


class ReferenceRouter(Router):
    def decide(self, req, now_ms, fleet_view):
        for name, view in fleet_view.items():
            if req.model_requested in view["models"]:
                return Action("dispatch", provider=name, model=req.model_requested)
        return Action("defer", until_ms=now_ms + 1000)
