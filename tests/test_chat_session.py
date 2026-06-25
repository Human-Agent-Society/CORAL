"""Tests for the interactive chat bridge (coral/chat/session.py).

The bridge is exercised against a *mock* `claude` — a small Python script
that speaks the same stream-json protocol the real CLI does (pinned against
claude 2.1.153). This keeps the test deterministic and free of API cost /
network, while still covering spawn → stdin send → stdout parse → frame
fan-out → transcript replay → clean close.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from coral.chat.session import CLOSED_FRAME_TYPE, ChatSessionManager

# Mock `claude`: emit a system/init frame, then for each user frame on stdin
# emit an assistant + result frame echoing the text. Exits on stdin EOF.
_FAKE_BODY = r"""
import sys, json

def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

emit({"type": "system", "subtype": "init", "session_id": "fake-sess", "model": "fake"})
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    text = msg["message"]["content"][0]["text"]
    emit({"type": "assistant",
          "message": {"role": "assistant", "content": [{"type": "text", "text": "echo: " + text}]},
          "session_id": "fake-sess"})
    emit({"type": "result", "subtype": "success", "is_error": False,
          "result": "echo: " + text, "session_id": "fake-sess"})
"""


def _write_fake_claude(tmp_path: Path) -> Path:
    script = tmp_path / "fake-claude"
    # Pin the interpreter via the shebang so the spawn matches this env.
    script.write_text(f"#!{sys.executable}\n{_FAKE_BODY}")
    script.chmod(0o755)
    return script


def test_chat_bridge_echo_round_trip(tmp_path: Path) -> None:
    fake = _write_fake_claude(tmp_path)

    async def inner():
        mgr = ChatSessionManager()
        session = mgr.create(workdir=tmp_path, claude_bin=str(fake))
        queue = session.subscribe()
        session.send("hello")
        frames = []
        while True:
            frame = await asyncio.wait_for(queue.get(), timeout=10)
            frames.append(frame)
            if frame.get("type") == "result":
                break
        claude_sid = session.claude_session_id
        mgr.shutdown()
        return frames, claude_sid

    frames, claude_sid = asyncio.run(inner())

    types = [f.get("type") for f in frames]
    assert "system" in types  # init frame relayed
    assert "assistant" in types
    assert frames[-1]["type"] == "result"
    assert frames[-1]["result"] == "echo: hello"

    # claude's own session id was captured from the init frame
    assert claude_sid == "fake-sess"

    # the assistant text block was relayed verbatim
    assistant = next(f for f in frames if f.get("type") == "assistant")
    assert assistant["message"]["content"][0]["text"] == "echo: hello"


def test_chat_session_emits_closed_frame_on_exit(tmp_path: Path) -> None:
    fake = _write_fake_claude(tmp_path)

    async def inner():
        mgr = ChatSessionManager()
        session = mgr.create(workdir=tmp_path, claude_bin=str(fake))
        queue = session.subscribe()
        # Wait until the init frame actually arrives before tearing down, so
        # the test never races the subprocess's cold start (a fixed sleep can
        # let stop() kill the mock before it has emitted anything).
        first = await asyncio.wait_for(queue.get(), timeout=10)
        session.stop()  # closes stdin → fake hits EOF → exits
        frames = [first]
        while True:
            frame = await asyncio.wait_for(queue.get(), timeout=10)
            frames.append(frame)
            if frame.get("type") == CLOSED_FRAME_TYPE:
                break
        mgr.shutdown()
        return frames

    frames = asyncio.run(inner())
    types = [f.get("type") for f in frames]
    assert "system" in types
    assert types[-1] == CLOSED_FRAME_TYPE


def test_manager_get_and_close(tmp_path: Path) -> None:
    fake = _write_fake_claude(tmp_path)

    async def inner():
        mgr = ChatSessionManager()
        session = mgr.create(workdir=tmp_path, claude_bin=str(fake))
        sid = session.session_id
        assert mgr.get(sid) is session
        assert mgr.close(sid) is True
        assert mgr.get(sid) is None
        assert mgr.close(sid) is False  # idempotent / unknown id
        assert not session.alive

    asyncio.run(inner())
