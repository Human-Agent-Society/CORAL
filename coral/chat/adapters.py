"""Per-runtime interactive adapters for the chat module.

Two interaction models (see chat-runtime-protocols):

  - ``streaming`` (claude_code): one long-lived process; user messages are
    written to stdin as JSON frames; output frames stream back continuously.
  - ``per_turn`` (codex, opencode): each user message spawns a fresh process
    (``codex exec`` / ``opencode run``); context is preserved via session
    resume; output is read to completion, then the process exits.

Each adapter normalizes its runtime's events into the common chat frame
schema the web UI renders — the claude shape:

    {"type":"system","subtype":"init", ...}
    {"type":"assistant","message":{"content":[{"type":"text"|"tool_use", ...}]}}
    {"type":"result","is_error":bool, ...}

Per decision A, codex/opencode run with approvals bypassed (single-user host =
trust boundary); the ``coral start`` approval hook is claude-only.
"""

from __future__ import annotations

import json
from typing import Any

STREAMING = "streaming"
PER_TURN = "per_turn"

_ALIASES = {
    "claude": "claude_code",
    "claude-code": "claude_code",
    "claude_code": "claude_code",
    "codex": "codex",
    "openai": "codex",
    "openai-codex": "codex",
    "opencode": "opencode",
    "open-code": "opencode",
}


def canonical_runtime(name: str | None) -> str:
    n = (name or "").strip()
    return _ALIASES.get(n, n)


def supported_runtimes() -> list[str]:
    return ["claude_code", "codex", "opencode"]


class ChatAdapter:
    """Base adapter. Subclasses set ``runtime``/``mode``/``binary`` and override
    the methods relevant to their interaction model."""

    runtime: str = ""
    mode: str = STREAMING
    binary: str = ""

    # streaming-mode hooks ------------------------------------------------
    def build_streaming_command(
        self,
        binary: str,
        model: str | None,
        extra_args: list[str] | None,
        settings_json: str | None,
    ) -> list[str]:
        raise NotImplementedError

    def encode_user_message(self, text: str) -> str:
        raise NotImplementedError

    # per-turn-mode hooks -------------------------------------------------
    def build_turn_command(
        self,
        binary: str,
        model: str | None,
        text: str,
        resume_id: str | None,
        extra_args: list[str] | None,
    ) -> list[str]:
        raise NotImplementedError

    # both ----------------------------------------------------------------
    def normalize(self, obj: dict[str, Any]) -> dict[str, Any] | None:
        """Map one raw runtime event to a common chat frame, or None to drop."""
        return obj

    def session_id_from(self, obj: dict[str, Any]) -> str | None:
        """Extract the runtime's session/thread id (for resume), if present."""
        return None


class ClaudeAdapter(ChatAdapter):
    runtime = "claude_code"
    mode = STREAMING
    binary = "claude"

    def build_streaming_command(self, binary, model, extra_args, settings_json):
        cmd = [
            binary or self.binary,
            "--print",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
        ]
        if model:
            cmd += ["--model", model]
        if settings_json:
            cmd += ["--settings", settings_json]
        if extra_args:
            cmd += list(extra_args)
        return cmd

    def encode_user_message(self, text):
        return (
            json.dumps(
                {
                    "type": "user",
                    "message": {"role": "user", "content": [{"type": "text", "text": text}]},
                }
            )
            + "\n"
        )

    def normalize(self, obj):
        # claude frames already match the target schema.
        return obj

    def session_id_from(self, obj):
        if obj.get("type") == "system" and obj.get("subtype") == "init":
            sid = obj.get("session_id")
            return sid if isinstance(sid, str) else None
        return None


class CodexAdapter(ChatAdapter):
    runtime = "codex"
    mode = PER_TURN
    binary = "codex"

    def build_turn_command(self, binary, model, text, resume_id, extra_args):
        cmd = [binary or self.binary, "exec"]
        if resume_id:
            cmd += ["resume", resume_id]
        cmd += [
            text,
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
        ]
        if model:
            cmd += ["--model", model]
        if extra_args:
            cmd += list(extra_args)
        cmd += ["--json"]
        return cmd

    def normalize(self, obj):
        t = obj.get("type")
        if t == "item.completed":
            item = obj.get("item") or {}
            if item.get("type") == "agent_message":
                return {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": item.get("text", "")}]},
                }
            # any other item type is tool-ish activity (command_execution, ...)
            return {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": str(item.get("type") or "tool"), "input": item}
                    ]
                },
            }
        if t == "turn.completed":
            return {"type": "result", "is_error": False, "usage": obj.get("usage")}
        if t == "error" or (isinstance(t, str) and t.endswith(".failed")):
            return {
                "type": "result",
                "is_error": True,
                "result": json.dumps(obj.get("error") or obj)[:500],
            }
        # thread.started (sid captured via session_id_from), turn.started,
        # item.started, reasoning, etc. → dropped.
        return None

    def session_id_from(self, obj):
        if obj.get("type") == "thread.started":
            tid = obj.get("thread_id")
            if isinstance(tid, str):
                return tid
        sid = obj.get("session_id")
        return sid if isinstance(sid, str) else None


def _extract_opencode_text(obj: dict[str, Any]) -> str | None:
    """Best-effort text extraction from an opencode event (schema unverified)."""
    for key in ("text", "content"):
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            return v
    part = obj.get("part")
    if isinstance(part, dict) and isinstance(part.get("text"), str):
        return part["text"]
    msg = obj.get("message")
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            texts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            joined = "".join(texts)
            if joined.strip():
                return joined
    return None


class OpenCodeAdapter(ChatAdapter):
    runtime = "opencode"
    mode = PER_TURN
    binary = "opencode"

    _DONE_TYPES = {"session.idle", "session.completed", "done", "finish", "complete", "step-finish"}

    def build_turn_command(self, binary, model, text, resume_id, extra_args):
        cmd = [binary or self.binary, "run", "--format", "json"]
        if model:
            cmd += ["--model", model]
        if resume_id:
            cmd += ["--continue", "--session", resume_id]
        if extra_args:
            cmd += list(extra_args)
        cmd += [text]
        return cmd

    def normalize(self, obj):
        # NOTE: opencode's success-event schema is unverified on this host
        # (default provider auth 401s), so parsing is defensive.
        t = obj.get("type")
        if t == "error":
            err = obj.get("error") or {}
            data = err.get("data") if isinstance(err, dict) else None
            msg = None
            if isinstance(data, dict):
                msg = data.get("message")
            msg = (
                msg or (err.get("name") if isinstance(err, dict) else None) or json.dumps(err)[:300]
            )
            return {"type": "result", "is_error": True, "result": str(msg)}
        text = _extract_opencode_text(obj)
        if text:
            return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}
        if t in self._DONE_TYPES:
            return {"type": "result", "is_error": False}
        return None

    def session_id_from(self, obj):
        for key in ("sessionID", "session_id", "sessionId"):
            v = obj.get(key)
            if isinstance(v, str):
                return v
        return None


_ADAPTERS = {
    "claude_code": ClaudeAdapter,
    "codex": CodexAdapter,
    "opencode": OpenCodeAdapter,
}


def get_adapter(runtime: str | None) -> ChatAdapter:
    r = canonical_runtime(runtime) or "claude_code"
    cls = _ADAPTERS.get(r)
    if cls is None:
        raise ValueError(
            f"chat does not support runtime {runtime!r} "
            f"(supported: {', '.join(supported_runtimes())})"
        )
    return cls()
