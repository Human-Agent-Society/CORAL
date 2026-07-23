"""Tests for the PreToolUse approval hook (coral/hooks/pretooluse_gate.py).

The network round-trip is exercised against a tiny localhost HTTP server,
so request_approval / fail-closed behaviour is covered without mocking out
urllib.
"""

from __future__ import annotations

import io
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from coral.hooks import pretooluse_gate as gate


def test_is_gated_bypass_mode_only_gates_coral_start() -> None:
    assert gate.is_gated("Bash", {"command": "coral start -c task.yaml"}, "bypass") is True
    assert gate.is_gated("Bash", {"command": "   coral start"}, "bypass") is True
    assert gate.is_gated("Bash", {"command": "ls -la"}, "bypass") is False
    assert gate.is_gated("Bash", {"command": "coral status"}, "bypass") is False
    assert gate.is_gated("Write", {"file_path": "x"}, "bypass") is False
    assert gate.is_gated("Edit", {}, "bypass") is False


def test_is_gated_strict_and_unknown_modes_fail_closed() -> None:
    for mode in ("approve_writes", "weird-unknown-mode"):
        assert gate.is_gated("Write", {}, mode) is True
        assert gate.is_gated("Edit", {}, mode) is True
        assert gate.is_gated("Bash", {"command": "ls"}, mode) is True
        assert gate.is_gated("Read", {}, mode) is False


def test_decision_payload_shape() -> None:
    hso = gate.decision_payload("allow")["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "allow"
    assert hso["permissionDecisionReason"]


def test_request_approval_fail_closed_without_config() -> None:
    assert (
        gate.request_approval(
            session_id="s", tool_name="Bash", tool_input={}, callback_url="", callback_token=""
        )
        == "deny"
    )


def test_request_approval_fail_closed_on_unreachable() -> None:
    assert (
        gate.request_approval(
            session_id="s",
            tool_name="Bash",
            tool_input={},
            callback_url="http://127.0.0.1:1",
            callback_token="tok",
        )
        == "deny"
    )


class _Handler(BaseHTTPRequestHandler):
    decision = "allow"
    token_seen: str | None = None

    def do_POST(self) -> None:  # noqa: N802 (stdlib API)
        _Handler.token_seen = self.headers.get("X-Coral-Callback-Token")
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        resp = json.dumps({"decision": _Handler.decision}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, *args) -> None:  # silence test server logging
        pass


@pytest.fixture
def mock_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def test_request_approval_allow(mock_server: str) -> None:
    _Handler.decision = "allow"
    out = gate.request_approval(
        session_id="s",
        tool_name="Bash",
        tool_input={"command": "coral start"},
        callback_url=mock_server,
        callback_token="tok",
    )
    assert out == "allow"
    assert _Handler.token_seen == "tok"  # token forwarded in the header


def test_request_approval_deny(mock_server: str) -> None:
    _Handler.decision = "deny"
    out = gate.request_approval(
        session_id="s",
        tool_name="Bash",
        tool_input={"command": "coral start"},
        callback_url=mock_server,
        callback_token="tok",
    )
    assert out == "deny"


def test_main_allows_ungated(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})),
    )
    monkeypatch.setenv("CORAL_CHAT_GATE_MODE", "bypass")
    rc = gate.main()
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_main_gated_denies_without_callback(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": "coral start"}})),
    )
    monkeypatch.setenv("CORAL_CHAT_GATE_MODE", "bypass")
    monkeypatch.delenv("CORAL_CHAT_CALLBACK_URL", raising=False)
    monkeypatch.delenv("CORAL_CHAT_CALLBACK_TOKEN", raising=False)
    rc = gate.main()
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
