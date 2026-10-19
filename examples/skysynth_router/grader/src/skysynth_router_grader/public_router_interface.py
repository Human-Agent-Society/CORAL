"""Router policy interface, public edition. Staged beside every candidate as
``evaluator/router_interface.py`` so ``from evaluator.router_interface import
Action, Router`` works exactly as upstream's task.md describes.

Identical to upstream's file except that ``Request`` has no ``quality`` and
no ``quality_floor``: this study keeps ground truth evaluator-private at
decision time, so the candidate-side type simply has no such attributes. The
harness owns the clock, the fleet, billing, and all correctness/SLO
accounting; the router owns only placement policy.

Public per-request signals live in ``features``: ``tenant``, ``task``,
``prompt_id``, ``difficulty_hint``, and ``pred`` (the supplied predictor's
score per fleet model for this prompt, when available).
"""

from dataclasses import dataclass


@dataclass
class Request:
    """One trace record, as the router sees it."""

    req_id: int
    t_ms: int
    session_id: str
    cls: str
    model_requested: str
    equiv_class: list
    prompt_tokens: int
    prefix_id: str
    prefix_tokens: int
    expected_output_tokens: int
    max_tokens: int
    stream: bool
    slo: dict
    downgrade_ok: bool
    retry_safe: bool
    temperature: float
    # observable per-request features a deployed router may legitimately use
    features: dict = None  # type: ignore[assignment]

    @classmethod
    def from_json(cls, d):
        return cls(
            req_id=d["req_id"],
            t_ms=d["t_ms"],
            session_id=d["session_id"],
            cls=d["class"],
            model_requested=d["model_requested"],
            equiv_class=d["equiv_class"],
            prompt_tokens=d["prompt_tokens"],
            prefix_id=d["prefix_id"],
            prefix_tokens=d["prefix_tokens"],
            expected_output_tokens=d["expected_output_tokens"],
            max_tokens=d["max_tokens"],
            stream=d["stream"],
            slo=d["slo"],
            downgrade_ok=d["downgrade_ok"],
            retry_safe=d["retry_safe"],
            temperature=d["temperature"],
            features=d.get("features", {}),
        )


@dataclass
class Action:
    """DISPATCH(provider, model) sends now; DEFER(until_ms) re-invokes decide() at that
    time; SHED rejects explicitly (legal only under declared overload)."""

    kind: str  # "dispatch" | "defer" | "shed"
    provider: str | None = None
    model: str | None = None
    until_ms: int | None = None


class Router:
    """Subclass and implement decide(). The fleet_view is read-only truth about the fleet:
    {name: {"models": {model: {"in","out","cached"}}, "inflight": int, "rpm_left": int,
    "tpm_left": int, "error_rate": float, "has_prefix": callable(prefix_id)->bool}}.
    A provider in an announced outage publishes an empty "models" catalogue and an
    "outage_until" timestamp. Mutating the view is a correctness violation."""

    def decide(self, req: Request, now_ms: int, fleet_view: dict) -> Action:
        raise NotImplementedError

    def on_error(self, req: Request, now_ms: int, kind: str, retry_after_ms: int) -> None:
        """Informational: a dispatch failed (429/503). decide() is re-invoked afterwards."""

    def on_complete(self, req: Request, now_ms: int) -> Action | None:
        """Informational hook after a request completes. A correct router returns None."""
        return None
