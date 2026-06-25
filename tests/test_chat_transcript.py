"""Tests for chat transcript persistence (coral/chat/transcript.py)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from coral.chat.session import ChatSessionManager
from coral.chat.transcript import (
    ChatTranscript,
    list_sessions,
    read_meta,
    read_transcript,
)

_FAKE_BODY = r"""
import sys, json

def emit(o):
    sys.stdout.write(json.dumps(o) + "\n")
    sys.stdout.flush()

emit({"type": "system", "subtype": "init", "session_id": "fake", "model": "fake"})
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    m = json.loads(line)
    text = m["message"]["content"][0]["text"]
    emit({"type": "assistant",
          "message": {"role": "assistant", "content": [{"type": "text", "text": "echo: " + text}]},
          "session_id": "fake"})
    emit({"type": "result", "subtype": "success", "is_error": False,
          "result": "echo: " + text, "session_id": "fake"})
"""


def _write_fake_claude(tmp_path: Path) -> Path:
    script = tmp_path / "fake-claude"
    script.write_text(f"#!{sys.executable}\n{_FAKE_BODY}")
    script.chmod(0o755)
    return script


def test_transcript_round_trip(tmp_path: Path) -> None:
    t = ChatTranscript("s1", root=tmp_path)
    t.open({"workdir": "/x", "model": "m"})
    t.append({"type": "system", "n": 1})
    t.append({"type": "result", "n": 2})
    t.close()

    frames = read_transcript("s1", root=tmp_path)
    assert [f["n"] for f in frames] == [1, 2]

    meta = read_meta("s1", root=tmp_path)
    assert meta is not None
    assert meta["session_id"] == "s1"
    assert meta["workdir"] == "/x"
    assert meta["model"] == "m"
    assert "created_at" in meta


def test_read_unknown_is_empty(tmp_path: Path) -> None:
    assert read_transcript("nope", root=tmp_path) == []
    assert read_meta("nope", root=tmp_path) is None
    assert list_sessions(root=tmp_path) == []


def test_list_sessions(tmp_path: Path) -> None:
    for sid in ("a", "b"):
        t = ChatTranscript(sid, root=tmp_path)
        t.open()
        t.close()
    ids = {s["session_id"] for s in list_sessions(root=tmp_path)}
    assert ids == {"a", "b"}


def test_session_persists_frames_to_disk(tmp_path: Path) -> None:
    fake = _write_fake_claude(tmp_path)
    root = tmp_path / "transcripts"

    async def inner():
        mgr = ChatSessionManager()
        session = mgr.create(workdir=tmp_path, claude_bin=str(fake), transcript_root=root)
        queue = session.subscribe()
        session.send("hello")
        while True:
            frame = await asyncio.wait_for(queue.get(), timeout=10)
            if frame.get("type") == "result":
                break
        sid = session.session_id
        mgr.shutdown()
        return sid

    sid = asyncio.run(inner())

    frames = read_transcript(sid, root=root)
    types = [f.get("type") for f in frames]
    assert "system" in types
    assert "result" in types
    assert any(f.get("result") == "echo: hello" for f in frames if f.get("type") == "result")
    assert read_meta(sid, root=root)["workdir"] == str(tmp_path)
