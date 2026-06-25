"""Tests for the chat approval registry (coral/chat/approval.py)."""

from __future__ import annotations

import asyncio

from coral.chat.approval import ApprovalRegistry


def test_resolve_unblocks_wait() -> None:
    async def inner():
        reg = ApprovalRegistry()
        reg.create("p1", {"tool_name": "Bash"})
        waiter = asyncio.create_task(reg.wait("p1", timeout=5))
        await asyncio.sleep(0)  # let the waiter reach its await point
        resolved = reg.resolve("p1", "allow")
        return resolved, await waiter

    resolved, decision = asyncio.run(inner())
    assert resolved is True
    assert decision == "allow"


def test_timeout_denies() -> None:
    async def inner():
        reg = ApprovalRegistry()
        reg.create("p1")
        return await reg.wait("p1", timeout=0.1)

    assert asyncio.run(inner()) == "deny"


def test_resolve_unknown_returns_false() -> None:
    async def inner():
        reg = ApprovalRegistry()
        return reg.resolve("nope", "allow")

    assert asyncio.run(inner()) is False


def test_wait_unknown_denies() -> None:
    async def inner():
        reg = ApprovalRegistry()
        return await reg.wait("nope", timeout=0.1)

    assert asyncio.run(inner()) == "deny"


def test_double_resolve_is_false_after_completion() -> None:
    async def inner():
        reg = ApprovalRegistry()
        reg.create("p1")
        waiter = asyncio.create_task(reg.wait("p1", timeout=5))
        await asyncio.sleep(0)
        first = reg.resolve("p1", "allow")
        await waiter  # wait() pops the entry in its finally
        second = reg.resolve("p1", "deny")
        return first, second

    first, second = asyncio.run(inner())
    assert first is True
    assert second is False


def test_pending_exposes_meta() -> None:
    async def inner():
        reg = ApprovalRegistry()
        reg.create("p1", {"tool_name": "Bash", "session_id": "s1"})
        return reg.pending()

    assert asyncio.run(inner()) == [{"prompt_id": "p1", "tool_name": "Bash", "session_id": "s1"}]
