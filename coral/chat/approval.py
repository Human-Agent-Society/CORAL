"""Approval registry for the chat `coral start` gate (P3).

The PreToolUse hook (``coral/hooks/pretooluse_gate.py``) POSTs to a
localhost callback when it intercepts a gated tool call; that handler parks
the request here and awaits the user's decision, which the UI delivers via
the resolve route. Both the park (internal callback) and the resolve (UI)
run on the same event loop, so a plain ``asyncio.Future`` bridges them.
"""

from __future__ import annotations

import asyncio
from typing import Any


class ApprovalRegistry:
    """Pending tool-approval requests keyed by ``prompt_id``."""

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[str]] = {}
        self._meta: dict[str, dict[str, Any]] = {}

    def create(self, prompt_id: str, meta: dict[str, Any] | None = None) -> asyncio.Future[str]:
        """Register a pending approval; returns the future the waiter awaits."""
        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._pending[prompt_id] = fut
        self._meta[prompt_id] = meta or {}
        return fut

    async def wait(self, prompt_id: str, timeout: float = 300.0) -> str:
        """Block until resolved or timed out. Fail-closed → "deny"."""
        fut = self._pending.get(prompt_id)
        if fut is None:
            return "deny"
        try:
            return await asyncio.wait_for(fut, timeout)
        except (TimeoutError, asyncio.CancelledError):
            return "deny"
        finally:
            self._pending.pop(prompt_id, None)
            self._meta.pop(prompt_id, None)

    def resolve(self, prompt_id: str, decision: str) -> bool:
        """Deliver a decision to a waiting approval. Returns False if unknown."""
        fut = self._pending.get(prompt_id)
        if fut is None or fut.done():
            return False
        fut.set_result(decision)
        return True

    def pending(self) -> list[dict[str, Any]]:
        return [{"prompt_id": pid, **meta} for pid, meta in self._meta.items()]
