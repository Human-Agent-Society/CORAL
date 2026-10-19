"""The candidate process. Runs inside the OS sandbox; speaks JSON lines.

Loads ``solution.py`` from its working directory, instantiates one router per
tenant, and answers ``decide`` / ``on_error`` / ``on_complete`` calls from the
trusted replay over stdin/stdout. It never sees ``quality``: the trusted side
already removed it, and the ``Request`` type available here has no such field.

Nothing in this file is privileged. It is deliberately stdlib-only so the
sandbox can allow the interpreter and this directory and nothing else.

Protocol (one JSON object per line, request then reply):

    {"op": "init", "classes": {"A": "InteractiveRouter", "B": "BatchRouter"}}
        -> {"ok": true} | {"error": "..."}
    {"op": "decide", "tenant": "A", "row": 17, "req": {...}, "now_ms": 1, "fleet": {...}}
        -> {"action": {...}} | {"action": null} | {"error": "..."}
    {"op": "on_error", "tenant": "A", "row": 17, "req": {...}, "now_ms": 1,
     "kind": "429", "retry_after_ms": 2000}
        -> {"ok": true} | {"error": "..."}
    {"op": "on_complete", "tenant": "A", "row": 17, "req": {...}, "now_ms": 1}
        -> {"action": {...} | null} | {"error": "..."}
    {"op": "release", "row": 17}   # forget the cached Request for this row
        -> {"ok": true}

The same ``Request`` object is handed to every callback for one row, as
upstream does, so a policy may key on it. ``release`` frees it once the row
is settled.
"""

from __future__ import annotations

import importlib.util
import json
import os
import resource
import sys
import traceback
from typing import Any

MEMORY_LIMIT_BYTES = int(os.environ.get("ROUTER_WORKER_MEMORY_BYTES", str(2 * 1024**3)))


def _limit_resources() -> None:
    try:
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    except (ValueError, OSError):  # pragma: no cover - platform dependent
        pass
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    except (ValueError, OSError):  # pragma: no cover
        pass


def _load_solution(path: str):
    spec = importlib.util.spec_from_file_location("solution", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["solution"] = module
    spec.loader.exec_module(module)
    return module


def _request_from_public(d: dict[str, Any]):
    from evaluator.router_interface import Request  # public copy staged beside us

    return Request(
        req_id=d.get("req_id"),
        t_ms=d.get("t_ms"),
        session_id=d.get("session_id"),
        cls=d.get("class"),
        model_requested=d.get("model_requested"),
        equiv_class=list(d.get("equiv_class") or []),
        prompt_tokens=d.get("prompt_tokens"),
        prefix_id=d.get("prefix_id"),
        prefix_tokens=d.get("prefix_tokens"),
        expected_output_tokens=d.get("expected_output_tokens"),
        max_tokens=d.get("max_tokens"),
        stream=d.get("stream"),
        slo=dict(d.get("slo") or {}),
        downgrade_ok=d.get("downgrade_ok"),
        retry_safe=d.get("retry_safe"),
        temperature=d.get("temperature"),
        features=dict(d.get("features") or {}),
    )


def _fleet_from_public(view: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, entry in view.items():
        warm = frozenset(entry.get("warm_prefixes") or ())
        e = {k: v for k, v in entry.items() if k != "warm_prefixes"}
        e["has_prefix"] = lambda pid, _w=warm: pid in _w
        out[name] = e
    return out


def _action_to_json(action: Any) -> dict[str, Any] | None:
    if action is None:
        return None
    return {
        "kind": getattr(action, "kind", None),
        "provider": getattr(action, "provider", None),
        "model": getattr(action, "model", None),
        "until_ms": getattr(action, "until_ms", None),
    }


class Worker:
    def __init__(self) -> None:
        self.routers: dict[str, Any] = {}
        self.requests: dict[int, Any] = {}

    def init(self, msg: dict[str, Any]) -> dict[str, Any]:
        module = _load_solution(msg.get("solution_path") or "solution.py")
        for tenant, cls_name in (msg.get("classes") or {}).items():
            cls = getattr(module, cls_name, None)
            if cls is None:
                raise AttributeError(f"solution.py does not define {cls_name}")
            self.routers[tenant] = cls()
        return {"ok": True}

    def _router(self, tenant: str) -> Any:
        r = self.routers.get(tenant)
        if r is None:
            raise KeyError(f"no router for tenant {tenant!r}")
        return r

    def _req(self, msg: dict[str, Any]) -> Any:
        row = int(msg["row"])
        req = self.requests.get(row)
        if req is None:
            req = self.requests[row] = _request_from_public(msg["req"])
        return req

    def handle(self, msg: dict[str, Any]) -> dict[str, Any]:
        op = msg.get("op")
        if op == "init":
            return self.init(msg)
        if op == "release":
            self.requests.pop(int(msg["row"]), None)
            return {"ok": True}
        if op == "decide":
            router = self._router(msg["tenant"])
            action = router.decide(
                self._req(msg), int(msg["now_ms"]), _fleet_from_public(msg["fleet"])
            )
            return {"action": _action_to_json(action)}
        if op == "on_error":
            router = self._router(msg["tenant"])
            router.on_error(
                self._req(msg), int(msg["now_ms"]), msg["kind"], int(msg["retry_after_ms"])
            )
            return {"ok": True}
        if op == "on_complete":
            router = self._router(msg["tenant"])
            action = router.on_complete(self._req(msg), int(msg["now_ms"]))
            return {"action": _action_to_json(action)}
        raise ValueError(f"unknown op {op!r}")


def main() -> int:
    _limit_resources()
    sys.path.insert(0, os.getcwd())
    worker = Worker()
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            reply = worker.handle(msg)
        except Exception as exc:  # any candidate fault becomes a typed reply
            reply = {
                "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                "traceback": traceback.format_exc()[-1500:],
            }
        try:
            out.write(json.dumps(reply, default=str) + "\n")
        except (TypeError, ValueError) as exc:
            out.write(json.dumps({"error": f"unserializable reply: {exc}"}) + "\n")
        out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
