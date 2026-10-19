"""The trusted-side ``Router`` that forwards every callback to the sandboxed worker.

Plugs into upstream's ``TenantReplay.run`` unchanged: upstream hands it the
router-facing request copy, the clock and the fleet view exactly as it would
hand them to an in-process policy. This class projects the request through
``boundary.public_request`` (removing ground truth), serializes the fleet
view, and forwards to one worker process that holds one router instance per
tenant. Both tenants therefore share one replay, one clock and one fleet, and
``decide`` / ``on_error`` / ``on_complete`` for a request all reach the same
instance.

Faults are typed, never swallowed. A candidate exception in the worker comes
back as a reply carrying ``error`` and is re-raised here, so upstream records
its usual ``router_exception`` violation against that request. A worker that
stops answering within ``call_timeout_s`` is killed and every later call
raises immediately; the replay then finishes its own accounting quickly (each
remaining request becomes a violation) and the candidate is invalid with the
nontermination recorded in ``faults``.
"""

from __future__ import annotations

import json
import select
import subprocess
import time
from pathlib import Path
from typing import Any

from skysynth_router_grader import boundary, sandbox


class CandidateFaultError(Exception):
    """A fault attributable to the candidate, surfaced to upstream as router_exception."""


class CandidateNonTerminationError(CandidateFaultError):
    """The worker did not answer within the per-call budget and was killed."""


class CandidateDeadError(CandidateFaultError):
    """The worker is gone; raised on every call after the fatal fault."""


class RemotePairRouter:
    """Upstream-compatible router facade over the sandboxed policy pair."""

    TENANT_CLASSES = {"A": "InteractiveRouter", "B": "BatchRouter"}

    def __init__(
        self,
        stage_dir: Path,
        *,
        predictions: dict[str, list[float]] | None = None,
        fleet: list[str] | None = None,
        call_timeout_s: float = 5.0,
        init_timeout_s: float = 30.0,
    ) -> None:
        self.stage_dir = Path(stage_dir)
        self.predictions = predictions
        self.fleet = fleet
        self.call_timeout_s = float(call_timeout_s)
        self.init_timeout_s = float(init_timeout_s)
        self.proc: subprocess.Popen[str] | None = None
        self.dead: str | None = None
        self.faults: list[dict[str, Any]] = []
        self.calls = 0
        self.max_call_ms = 0.0
        # per-request dispatch log for the adapter's diagnostics: last dispatched
        # (provider, model), the price the router saw for it, and completion
        self.dispatches: dict[int, dict[str, Any]] = {}
        self._rows: dict[int, tuple[int, Any, Any]] = {}
        self._next_row = 0
        self._start()

    # -- lifecycle ---------------------------------------------------------

    def _start(self) -> None:
        self.proc = sandbox.spawn(self.stage_dir)
        reply = self._rpc(
            {"op": "init", "solution_path": "solution.py", "classes": self.TENANT_CLASSES},
            timeout=self.init_timeout_s,
        )
        if "error" in reply:
            self._record_fault("init", reply)
            self._kill()
            self.dead = f"init failed: {reply['error']}"

    def close(self) -> None:
        self._kill()

    def _kill(self) -> None:
        p = self.proc
        if p is None:
            return
        try:
            if p.poll() is None:
                p.kill()
                p.wait(timeout=5)
        except Exception:  # noqa: BLE001 - best effort teardown
            pass
        for stream in (p.stdin, p.stdout, p.stderr):
            try:
                if stream:
                    stream.close()
            except Exception:  # noqa: BLE001
                pass

    def __del__(self) -> None:  # pragma: no cover - safety net
        self._kill()

    # -- transport ---------------------------------------------------------

    def _rpc(self, msg: dict[str, Any], *, timeout: float | None = None) -> dict[str, Any]:
        if self.dead is not None:
            raise CandidateDeadError(self.dead)
        p = self.proc
        if p is None or p.stdin is None or p.stdout is None:
            return self._fatal("worker not running", None)
        budget = self.call_timeout_s if timeout is None else timeout
        t0 = time.monotonic()
        try:
            p.stdin.write(json.dumps(msg, separators=(",", ":")) + "\n")
            p.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as exc:
            return self._fatal("worker pipe closed", exc)
        line = self._readline(p, budget)
        elapsed_ms = (time.monotonic() - t0) * 1000
        self.calls += 1
        self.max_call_ms = max(self.max_call_ms, elapsed_ms)
        if line is None:
            return self._fatal(f"no reply within {budget:.1f}s", None)
        try:
            reply = json.loads(line)
        except json.JSONDecodeError as exc:
            return self._fatal("worker reply was not JSON", exc)
        if not isinstance(reply, dict):
            return self._fatal("worker reply was not an object", None)
        return reply

    def _readline(self, p: subprocess.Popen[str], budget: float) -> str | None:
        """One line from the worker, or None on timeout / exit."""
        if p.stdout is None:
            return None
        deadline = time.monotonic() + budget
        fd = p.stdout.fileno()
        buf = ""
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            ready, _, _ = select.select([fd], [], [], min(remaining, 0.5))
            if not ready:
                if p.poll() is not None:
                    return None
                continue
            # TextIOWrapper.readline blocks only until "\n"; select said data is there.
            chunk = p.stdout.readline()
            if chunk == "":
                return None  # EOF
            buf += chunk
            if buf.endswith("\n"):
                return buf

    def _fatal(self, what: str, exc: BaseException | None) -> dict[str, Any]:
        stderr_tail = ""
        try:
            if self.proc is not None and self.proc.stderr is not None:
                self._kill()
        except Exception:  # noqa: BLE001
            pass
        detail = f"{what}" + (f": {type(exc).__name__}: {exc}" if exc else "")
        self.dead = detail
        self._record_fault("transport", {"error": detail, "stderr": stderr_tail})
        raise CandidateNonTerminationError(detail)

    def _record_fault(self, where: str, reply: dict[str, Any]) -> None:
        if len(self.faults) < 20:
            self.faults.append(
                {
                    "where": where,
                    "error": str(reply.get("error"))[:300],
                    "traceback": str(reply.get("traceback") or "")[-800:],
                }
            )

    # -- row identity ------------------------------------------------------

    def _row(self, req: Any) -> int:
        """Stable token per upstream proxy object.

        Keyed by object identity, verified against the request's own id and
        arrival time so a recycled ``id()`` cannot alias a settled row.
        """
        key = id(req)
        hit = self._rows.get(key)
        rid, t = getattr(req, "req_id", None), getattr(req, "t_ms", None)
        if hit is not None and hit[1] == rid and hit[2] == t:
            return hit[0]
        token = self._next_row
        self._next_row += 1
        self._rows[key] = (token, rid, t)
        return token

    def _release(self, req: Any) -> None:
        hit = self._rows.pop(id(req), None)
        if hit is None or self.dead is not None:
            return
        try:
            self._rpc({"op": "release", "row": hit[0]})
        except CandidateFaultError:
            pass

    # -- upstream Router interface ----------------------------------------

    def _payload(self, op: str, req: Any, now_ms: int, **extra: Any) -> dict[str, Any]:
        pub = boundary.public_request(req, self.predictions, self.fleet)
        tenant = (pub.get("features") or {}).get("tenant")
        if tenant not in self.TENANT_CLASSES:
            raise CandidateFaultError(f"request {pub.get('req_id')} carries no known tenant tag")
        return {
            "op": op,
            "tenant": tenant,
            "row": self._row(req),
            "req": pub,
            "now_ms": int(now_ms),
            **extra,
        }

    def _action(self, reply: dict[str, Any], what: str, req: Any):
        if "error" in reply:
            self._record_fault(what, reply)
            raise CandidateFaultError(reply["error"])
        try:
            act = boundary.validate_action(reply.get("action"))
        except ValueError as exc:
            self._record_fault(what, {"error": f"malformed action: {exc}"})
            raise CandidateFaultError(f"malformed action: {exc}") from exc
        if act is None:
            return None
        from evaluator.router_interface import Action  # upstream's own type

        return Action(
            act["kind"], provider=act["provider"], model=act["model"], until_ms=act["until_ms"]
        )

    def decide(self, req: Any, now_ms: int, fleet_view: dict[str, Any]):
        msg = self._payload("decide", req, now_ms, fleet=boundary.public_fleet_view(fleet_view))
        act = self._action(self._rpc(msg), "decide", req)
        if act is None:
            self._record_fault("decide", {"error": "decide() returned None"})
            raise CandidateFaultError("decide() returned None instead of an Action")
        if act.kind == "shed":
            self._release(req)
        elif act.kind == "dispatch":
            price = ((fleet_view.get(act.provider) or {}).get("models") or {}).get(act.model) or {}
            self.dispatches[int(req.req_id)] = {
                "provider": act.provider,
                "model": act.model,
                "price_in": price.get("in"),
                "price_out": price.get("out"),
                "completed": False,
            }
        return act

    def on_error(self, req: Any, now_ms: int, kind: str, retry_after_ms: int) -> None:
        reply = self._rpc(
            self._payload("on_error", req, now_ms, kind=kind, retry_after_ms=int(retry_after_ms))
        )
        if "error" in reply:
            self._record_fault("on_error", reply)
            raise CandidateFaultError(reply["error"])

    def on_complete(self, req: Any, now_ms: int):
        d = self.dispatches.get(int(req.req_id))
        if d is not None:
            d["completed"] = True
        reply = self._rpc(self._payload("on_complete", req, now_ms))
        try:
            return self._action(reply, "on_complete", req)
        finally:
            self._release(req)

    # -- reporting ---------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "max_call_ms": round(self.max_call_ms, 2),
            "dead": self.dead,
            "faults": list(self.faults),
        }
