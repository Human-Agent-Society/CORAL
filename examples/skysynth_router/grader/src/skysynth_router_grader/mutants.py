"""The correct reference pair and a library of deliberately broken variants.

A scenario check is admitted only if the reference passes it and the mutant
for its stated defect fails it. The mutants are the executable half of
"fails a broken copy with exactly the defect the test is for" (task.md):
each is a complete ``solution.py`` whose only departure from the reference
is the one named defect, so a check that fails it detects that defect and
not something incidental.

Every mutant is keyed by the invariant it violates. A proposal names an
``invariant_id``; the runner picks the mutant from this table. The proposer
never supplies executable code.
"""

from __future__ import annotations

REFERENCE_SOLUTION = '''"""Correct reference pair: the requested model on the first provider that lists it,
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
'''

_HEADER = "from evaluator.router_interface import Action, Router\n\n\n"

_REFERENCE_DECIDE = """    def decide(self, req, now_ms, fleet_view):
        for name, view in fleet_view.items():
            if req.model_requested in view["models"]:
                return Action("dispatch", provider=name, model=req.model_requested)
        return Action("defer", until_ms=now_ms + 1000)
"""


def _pair(body_a: str, body_b: str | None = None) -> str:
    b = body_b if body_b is not None else body_a
    return (
        _HEADER
        + "class InteractiveRouter(Router):\n"
        + body_a
        + "\n\nclass BatchRouter(Router):\n"
        + b
        + "\n"
    )


#: invariant_id -> (mutant_id, description, solution source)
MUTANTS: dict[str, tuple[str, str, str]] = {
    "no_outage_lost": (
        "outage_blind",
        "keeps dispatching to a provider that has announced an outage instead of "
        "rerouting or deferring; loses the request past the retry grace",
        _pair(
            """    def decide(self, req, now_ms, fleet_view):
        # picks a fixed provider by name and ignores its empty catalogue
        names = sorted(fleet_view)
        target = next((n for n in names if "outage_until" in fleet_view[n]), None)
        if target is None:
            for name, view in fleet_view.items():
                if req.model_requested in view["models"]:
                    return Action("dispatch", provider=name, model=req.model_requested)
            return Action("defer", until_ms=now_ms + 1000)
        return Action("dispatch", provider=target, model=req.model_requested)
"""
        ),
    ),
    "no_illegal_shed": (
        "shed_when_busy",
        "sheds a request as soon as one provider is saturated, even though another "
        "provider serving the model has headroom",
        _pair(
            """    def decide(self, req, now_ms, fleet_view):
        for name, view in fleet_view.items():
            if req.model_requested in view["models"]:
                if view["rpm_left"] <= 0 or view["inflight"] >= 4:
                    return Action("shed")
                return Action("dispatch", provider=name, model=req.model_requested)
        return Action("defer", until_ms=now_ms + 1000)
"""
        ),
    ),
    "no_illegal_substitution": (
        "always_substitutes",
        "dispatches the cheapest model on the fleet other than the one requested, "
        "ignoring the request's declared equivalence class and downgrade permission",
        _pair(
            """    def decide(self, req, now_ms, fleet_view):
        best = None
        for name, view in fleet_view.items():
            for model, price in view["models"].items():
                if model == req.model_requested:
                    continue
                key = (price["in"] + price["out"], model, name)
                if best is None or key < best[0]:
                    best = (key, name, model)
        if best is None:
            for name, view in fleet_view.items():
                if req.model_requested in view["models"]:
                    return Action("dispatch", provider=name, model=req.model_requested)
            return Action("defer", until_ms=now_ms + 1000)
        return Action("dispatch", provider=best[1], model=best[2])
"""
        ),
    ),
    "no_lost_request": (
        "defer_forever",
        "defers every request indefinitely instead of ever dispatching it",
        _pair(
            """    def decide(self, req, now_ms, fleet_view):
        return Action("defer", until_ms=now_ms + 60000)
"""
        ),
    ),
    "no_double_completion": (
        "redispatch_on_complete",
        "returns a dispatch action from on_complete, re-entering the harness and "
        "billing the request twice",
        _pair(
            _REFERENCE_DECIDE
            + """
    def on_complete(self, req, now_ms):
        for name, view in getattr(self, "_last_view", {}).items():
            if req.model_requested in view["models"]:
                return Action("dispatch", provider=name, model=req.model_requested)
        return Action("dispatch", provider="courier", model=req.model_requested)
"""
        ),
    ),
    "no_router_exception": (
        "batch_raises",
        "the batch tenant's router raises on every decision while the interactive "
        "router is correct",
        _pair(
            _REFERENCE_DECIDE,
            """    def decide(self, req, now_ms, fleet_view):
        raise RuntimeError("batch router broken on purpose")
""",
        ),
    ),
}


def mutant_for(invariant_id: str) -> tuple[str, str, str]:
    try:
        return MUTANTS[invariant_id]
    except KeyError:
        raise KeyError(f"no mutant library entry for invariant {invariant_id!r}") from None
