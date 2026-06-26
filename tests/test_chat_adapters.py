"""Tests for the per-runtime chat adapters (coral/chat/adapters.py).

Normalization is checked against the real event samples pinned by live
smoke tests (see chat-runtime-protocols): claude + codex are exact;
opencode is best-effort (its success schema is unverified on this host).
"""

from __future__ import annotations

import pytest

from coral.chat.adapters import (
    ClaudeAdapter,
    CodexAdapter,
    OpenCodeAdapter,
    canonical_runtime,
    get_adapter,
    supported_runtimes,
)


def test_canonical_runtime_and_factory() -> None:
    assert canonical_runtime("claude") == "claude_code"
    assert canonical_runtime("openai-codex") == "codex"
    assert canonical_runtime("open-code") == "opencode"
    assert isinstance(get_adapter("claude"), ClaudeAdapter)
    assert isinstance(get_adapter("codex"), CodexAdapter)
    assert isinstance(get_adapter("opencode"), OpenCodeAdapter)
    assert isinstance(get_adapter(None), ClaudeAdapter)  # default
    assert set(supported_runtimes()) == {"claude_code", "codex", "opencode"}
    with pytest.raises(ValueError):
        get_adapter("cursor_agent")


def test_claude_adapter() -> None:
    a = ClaudeAdapter()
    cmd = a.build_streaming_command("claude", "opus", None, '{"hooks":{}}')
    assert cmd[:6] == [
        "claude",
        "--print",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
    ]
    assert "--settings" in cmd and "--model" in cmd
    # input frame shape
    import json

    enc = json.loads(a.encode_user_message("hi"))
    assert enc == {
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]},
    }
    # frames pass through; session id from init
    frame = {"type": "assistant", "message": {"content": [{"type": "text", "text": "x"}]}}
    assert a.normalize(frame) is frame
    assert a.session_id_from({"type": "system", "subtype": "init", "session_id": "s1"}) == "s1"
    assert a.session_id_from({"type": "assistant"}) is None


def test_codex_adapter_command_and_events() -> None:
    a = CodexAdapter()
    first = a.build_turn_command("codex", "gpt-5.4", "hello", None, None)
    assert first[:2] == ["codex", "exec"]
    assert "hello" in first and "--json" in first
    assert "--skip-git-repo-check" in first
    assert "--dangerously-bypass-approvals-and-sandbox" in first
    resume = a.build_turn_command("codex", None, "again", "thr-9", None)
    assert resume[1:4] == ["exec", "resume", "thr-9"]

    # real codex event taxonomy
    assert a.session_id_from({"type": "thread.started", "thread_id": "019f"}) == "019f"
    assert a.normalize({"type": "thread.started", "thread_id": "019f"}) is None
    assert a.normalize({"type": "turn.started"}) is None

    text = a.normalize({"type": "item.completed", "item": {"type": "agent_message", "text": "OK"}})
    assert text == {"type": "assistant", "message": {"content": [{"type": "text", "text": "OK"}]}}

    tool = a.normalize(
        {"type": "item.completed", "item": {"type": "command_execution", "command": "ls"}}
    )
    assert tool["message"]["content"][0]["type"] == "tool_use"
    assert tool["message"]["content"][0]["name"] == "command_execution"

    done = a.normalize({"type": "turn.completed", "usage": {"output_tokens": 5}})
    assert done["type"] == "result" and done["is_error"] is False

    err = a.normalize({"type": "error", "error": {"message": "boom"}})
    assert err["type"] == "result" and err["is_error"] is True


def test_opencode_adapter_command_and_events() -> None:
    a = OpenCodeAdapter()
    cmd = a.build_turn_command("opencode", "openai/gpt-5", "hello", None, None)
    assert cmd[:4] == ["opencode", "run", "--format", "json"]
    assert cmd[-1] == "hello"
    resume = a.build_turn_command("opencode", None, "again", "ses_1", None)
    assert "--continue" in resume and "ses_1" in resume

    # session id from the observed envelope (sessionID)
    assert a.session_id_from({"type": "error", "sessionID": "ses_abc"}) == "ses_abc"

    # observed error event → result(is_error)
    err = a.normalize(
        {"type": "error", "sessionID": "ses_1", "error": {"data": {"message": "token is unusable"}}}
    )
    assert err["type"] == "result" and err["is_error"] is True
    assert "token is unusable" in err["result"]

    # defensive text extraction
    txt = a.normalize({"type": "text", "text": "hi there"})
    assert txt == {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "hi there"}]},
    }
    assert a.normalize({"type": "step-start"}) is None
