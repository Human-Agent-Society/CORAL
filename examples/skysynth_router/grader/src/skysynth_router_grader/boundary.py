"""What crosses from the trusted replay to the candidate, and nothing else.

Upstream's ``Request`` carries ``quality`` (ground-truth per-model scores) and
``quality_floor``; its interface leaves reading them to each experiment. This
study forbids it. The projection below is the single definition of the public
request, used identically by the grader's bridge and by the public replay tool
builders run locally, so a policy that behaves one way for the builder behaves
the same way for the grader.

The fleet view's ``has_prefix`` is a closure over a frozenset snapshot in the
trusted process. It cannot cross a process boundary as a callable, so the
snapshot itself crosses (``warm_prefixes``) and the candidate side rebuilds an
equivalent callable. Same semantics, same information.

Per-request predictions from the supplied trained predictor are attached to
``features["pred"]`` here, per request, so no candidate ever holds a table of
future prompt ids.
"""

from __future__ import annotations

from typing import Any

#: Trace fields the candidate never receives.
PRIVATE_REQUEST_FIELDS = ("quality", "quality_floor")

#: Fields a public request always has, in upstream's JSON spelling.
PUBLIC_REQUEST_FIELDS = (
    "req_id",
    "t_ms",
    "session_id",
    "class",
    "model_requested",
    "equiv_class",
    "prompt_tokens",
    "prefix_id",
    "prefix_tokens",
    "expected_output_tokens",
    "max_tokens",
    "stream",
    "slo",
    "downgrade_ok",
    "retry_safe",
    "temperature",
    "features",
)

#: Dataclass attribute -> JSON key, where they differ.
_ATTR_TO_JSON = {"cls": "class"}


def request_to_json(req: Any) -> dict[str, Any]:
    """Upstream ``Request`` dataclass (or a trace dict) -> trace-shaped dict."""
    if isinstance(req, dict):
        return dict(req)
    out: dict[str, Any] = {}
    for attr in (
        "req_id",
        "t_ms",
        "session_id",
        "cls",
        "model_requested",
        "equiv_class",
        "prompt_tokens",
        "prefix_id",
        "prefix_tokens",
        "expected_output_tokens",
        "max_tokens",
        "stream",
        "slo",
        "downgrade_ok",
        "retry_safe",
        "temperature",
        "quality",
        "quality_floor",
        "features",
    ):
        out[_ATTR_TO_JSON.get(attr, attr)] = getattr(req, attr, None)
    return out


def public_request(
    req: Any,
    predictions: dict[str, list[float]] | None = None,
    fleet: list[str] | None = None,
) -> dict[str, Any]:
    """The candidate-facing request: private fields removed, prediction attached.

    ``predictions`` maps ``prompt_id`` to a score list ordered as ``fleet``
    (upstream's ``generic_predictions.json`` layout). When present for this
    request, ``features["pred"]`` becomes ``{model: predicted_score}``.
    """
    d = request_to_json(req)
    for key in PRIVATE_REQUEST_FIELDS:
        d.pop(key, None)
    features = dict(d.get("features") or {})
    if predictions is not None and fleet is not None:
        scores = predictions.get(str(features.get("prompt_id")))
        if scores is not None:
            features["pred"] = {m: float(s) for m, s in zip(fleet, scores, strict=False)}
    d["features"] = features
    # Containers are copied so the trusted record is never aliased.
    d["equiv_class"] = list(d.get("equiv_class") or [])
    d["slo"] = dict(d.get("slo") or {})
    return {k: d.get(k) for k in PUBLIC_REQUEST_FIELDS}


def public_fleet_view(view: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Serializable fleet view. ``has_prefix`` becomes ``warm_prefixes``.

    Upstream builds each provider entry by value already (prices copied, counts
    as ints); only the callable needs replacing. Its closure is over a
    frozenset of warm prefix ids, which is reproduced exactly by probing the
    callable against nothing: the snapshot is not enumerable through the
    callable, so the replay's own ``_warm_prefixes`` is read via the closure
    default. Falls back to an empty set if a foreign view lacks it.
    """
    out: dict[str, dict[str, Any]] = {}
    for name, entry in view.items():
        pub = {k: v for k, v in entry.items() if k != "has_prefix"}
        pub["models"] = {m: dict(p) for m, p in (entry.get("models") or {}).items()}
        fn = entry.get("has_prefix")
        warm: set[str] = set()
        if fn is not None:
            # upstream: lambda pid, _w=<frozenset>: pid in _w
            defaults = getattr(fn, "__defaults__", None) or ()
            for value in defaults:
                if isinstance(value, (frozenset, set)):
                    warm = set(value)
                    break
        pub["warm_prefixes"] = sorted(warm)
        out[name] = pub
    return out


def validate_action(raw: Any) -> dict[str, Any] | None:
    """Coerce the candidate's serialized action or raise ``ValueError``.

    None means "no action" (legal from ``on_complete`` only; ``decide``
    returning None is a router fault and upstream records it).
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"action must be an object, got {type(raw).__name__}")
    kind = raw.get("kind")
    if kind not in ("dispatch", "defer", "shed"):
        raise ValueError(f"action.kind must be dispatch|defer|shed, got {kind!r}")
    provider = raw.get("provider")
    model = raw.get("model")
    until = raw.get("until_ms")
    if provider is not None and not isinstance(provider, str):
        raise ValueError("action.provider must be a string or null")
    if model is not None and not isinstance(model, str):
        raise ValueError("action.model must be a string or null")
    if until is not None:
        if isinstance(until, bool) or not isinstance(until, (int, float)):
            raise ValueError("action.until_ms must be a number or null")
        until = int(until)
    return {"kind": kind, "provider": provider, "model": model, "until_ms": until}
