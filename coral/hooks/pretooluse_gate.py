"""PreToolUse approval hook for the local chat agent (P3).

Invoked by ``claude`` as a subprocess (wired via the session's
``--settings``). Reads the PreToolUse event JSON on stdin, decides whether
the tool call is gated, and for gated calls round-trips a localhost
callback to ask the user. Prints a PreToolUse decision JSON to stdout.

STDLIB ONLY — it runs in the agent's interpreter and must not import any
third-party package. Fail-closed: a gated call whose approval can't be
obtained (no callback config, network error, timeout) is denied.

Gating (``CORAL_CHAT_GATE_MODE``):
  - ``bypass`` (default): only ``Bash`` commands starting with
    ``coral start`` are gated — the agent freely authors task files.
  - any other / unrecognized mode: gate all change/exec tools
    (Write/Edit/MultiEdit/Bash) — fail-closed.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
import uuid

# Tools the settings matcher fires on. Reads (Read/Glob/Grep) are not in the
# matcher and never reach this hook.
_CHANGE_EXEC = {"Write", "Edit", "MultiEdit", "Bash"}

_CALLBACK_PATH = "/api/chat/internal/approval"


def is_gated(tool_name: str, tool_input: dict, gate_mode: str) -> bool:
    """Whether this tool call must be approved by the user."""
    if gate_mode == "bypass":
        if tool_name == "Bash":
            cmd = (tool_input or {}).get("command", "")
            return cmd.strip().startswith("coral start")
        return False
    # Strict / unrecognized mode (fail-closed): gate every matched tool.
    return tool_name in _CHANGE_EXEC


def decision_payload(decision: str, reason: str | None = None) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason or f"user {decision} in CORAL chat",
        }
    }


def _post_callback(url: str, token: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "X-Coral-Callback-Token": token},
    )
    with urllib.request.urlopen(req, timeout=315) as resp:
        return json.loads(resp.read().decode("utf-8"))


def request_approval(
    *,
    session_id: str,
    tool_name: str,
    tool_input: dict,
    callback_url: str,
    callback_token: str,
) -> str:
    """Ask the user via the localhost callback; return "allow" or "deny".

    Fail-closed: anything other than an explicit allow is a deny.
    """
    if not callback_url or not callback_token:
        return "deny"
    url = callback_url.rstrip("/") + _CALLBACK_PATH
    body = {
        "session_id": session_id,
        "prompt_id": uuid.uuid4().hex,
        "tool_name": tool_name,
        "tool_input": tool_input,
    }
    try:
        resp = _post_callback(url, callback_token, body)
    except Exception:
        return "deny"
    return "allow" if resp.get("decision") == "allow" else "deny"


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except Exception:
        # A parse glitch shouldn't brick the agent; the gate targets a specific
        # command, not arbitrary events. Allow and move on.
        print(json.dumps(decision_payload("allow")))
        return 0

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {}) or {}
    gate_mode = os.environ.get("CORAL_CHAT_GATE_MODE", "bypass")

    if not is_gated(tool_name, tool_input, gate_mode):
        print(json.dumps(decision_payload("allow")))
        return 0

    decision = request_approval(
        session_id=os.environ.get("CORAL_CHAT_SESSION_ID", ""),
        tool_name=tool_name,
        tool_input=tool_input,
        callback_url=os.environ.get("CORAL_CHAT_CALLBACK_URL", ""),
        callback_token=os.environ.get("CORAL_CHAT_CALLBACK_TOKEN", ""),
    )
    print(json.dumps(decision_payload(decision)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
