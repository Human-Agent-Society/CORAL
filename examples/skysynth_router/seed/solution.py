"""Correct reference pair: the requested model on the first provider that lists it,
retry through harness wake-ups, never shed, no pacing. Slow and expensive on purpose."""

from evaluator.router_interface import Action, Router


class _Reference(Router):
    def decide(self, req, now_ms, fleet_view):
        for name, view in fleet_view.items():
            if req.model_requested in view["models"]:
                return Action("dispatch", provider=name, model=req.model_requested)
        return Action("defer", until_ms=now_ms + 1000)


class InteractiveRouter(_Reference):
    pass


class BatchRouter(_Reference):
    pass
