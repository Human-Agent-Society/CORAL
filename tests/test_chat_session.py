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
        session = mgr.create(workdir=tmp_path, binary=str(fake))
        queue = session.subscribe()
        session.send("hello")
        frames = []
        while True:
            frame = await asyncio.wait_for(queue.get(), timeout=10)
            frames.append(frame)
            if frame.get("type") == "result":
                break
        claude_sid = session.runtime_session_id
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
        session = mgr.create(workdir=tmp_path, binary=str(fake))
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
        session = mgr.create(workdir=tmp_path, binary=str(fake))
        sid = session.session_id
        assert mgr.get(sid) is session
        assert mgr.close(sid) is True
        assert mgr.get(sid) is None
        assert mgr.close(sid) is False  # idempotent / unknown id
        assert not session.alive

    asyncio.run(inner())


# Mock `codex`: codex-style JSONL. thread.started only on the first turn (no
# `resume` arg); echoes the positional message; emits a turn.completed.
_FAKE_CODEX = r"""
import sys, json

def emit(o):
    sys.stdout.write(json.dumps(o) + "\n")
    sys.stdout.flush()

args = sys.argv[1:]            # exec [resume <tid>] <text> --flags... --json
resume = "resume" in args
i = 1 if args[:1] == ["exec"] else 0
tid = ""
if args[i:i + 1] == ["resume"]:
    tid = args[i + 1] if i + 1 < len(args) else ""
    i += 2                     # skip 'resume' and the thread id
msg = args[i] if i < len(args) and not args[i].startswith("-") else ""

if not resume:
    emit({"type": "thread.started", "thread_id": "thr-1"})
emit({"type": "turn.started"})
prefix = ("resume " + tid + " ") if resume else ""
emit({"type": "item.completed", "item": {"id": "i0", "type": "agent_message", "text": "echo: " + prefix + msg}})
emit({"type": "turn.completed", "usage": {"output_tokens": 1}})
"""


def _write_mock_codex(tmp_path: Path) -> Path:
    script = tmp_path / "mock-codex"
    script.write_text(f"#!{sys.executable}\n{_FAKE_CODEX}")
    script.chmod(0o755)
    return script


def test_per_turn_session_spawns_per_message(tmp_path: Path) -> None:
    mock = _write_mock_codex(tmp_path)

    async def inner():
        mgr = ChatSessionManager()
        session = mgr.create(workdir=tmp_path, runtime="codex", binary=str(mock))
        queue = session.subscribe()
        # per_turn: alive without any persistent process, surfaced init frame.
        assert session.alive
        session.send("hi")
        frames = []
        while True:
            frame = await asyncio.wait_for(queue.get(), timeout=10)
            frames.append(frame)
            if frame.get("type") == "result":
                break
        rid = session.runtime_session_id
        mgr.shutdown()
        return frames, rid

    frames, rid = asyncio.run(inner())
    types = [f.get("type") for f in frames]
    assert "system" in types  # synthetic init (no thread.started shown)
    assistant = next(f for f in frames if f.get("type") == "assistant")
    assert assistant["message"]["content"][0]["text"] == "echo: hi"
    assert frames[-1]["type"] == "result" and frames[-1]["is_error"] is False
    assert rid == "thr-1"  # captured for resume on the next turn


def test_per_turn_resume_carries_context_across_turns(tmp_path: Path) -> None:
    """Turn 2 must spawn with turn 1's session id — context is preserved
    across the per-turn process boundary via resume."""
    mock = _write_mock_codex(tmp_path)

    async def inner():
        mgr = ChatSessionManager()
        session = mgr.create(workdir=tmp_path, runtime="codex", binary=str(mock))
        queue = session.subscribe()

        async def run_turn(text: str) -> dict:
            # wait until any prior turn has fully finished, then send.
            while session.busy():
                await asyncio.sleep(0.02)
            session.send(text)
            assistant = None
            while True:
                frame = await asyncio.wait_for(queue.get(), timeout=10)
                if frame.get("type") == "assistant":
                    assistant = frame
                if frame.get("type") == "result":
                    return assistant

        a1 = await run_turn("hi")
        a2 = await run_turn("again")
        rid = session.runtime_session_id
        mgr.shutdown()
        return a1, a2, rid

    a1, a2, rid = asyncio.run(inner())
    assert a1["message"]["content"][0]["text"] == "echo: hi"  # turn 1: fresh
    # turn 2 was spawned as `codex exec resume thr-1 again` — the captured
    # thread id flowed through, so the CLI reloads the conversation.
    assert a2["message"]["content"][0]["text"] == "echo: resume thr-1 again"
    assert rid == "thr-1"
