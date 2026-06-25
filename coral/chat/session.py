"""Interactive Claude Code chat session — a stream-json bridge.

P1 of the chat module (``design/chat-module.md``). Spawns ``claude`` in
interactive stream-json mode inside a working directory, relays user
messages onto its stdin, and broadcasts the output frames to subscribers
(the web SSE endpoint). No approval hook and no workspace gating yet —
those are P3 / P2.

Pinned against ``claude`` 2.1.153:

  claude --print --input-format stream-json --output-format stream-json --verbose [--model M]

  stdin  (newline-delimited JSON, kept open across turns until EOF):
    {"type":"user","message":{"role":"user","content":[{"type":"text","text":"..."}]}}
  stdout (newline-delimited JSON frames):
    {"type":"system","subtype":"init","session_id":...,"model":...,"cwd":...,"tools":[...]}
    {"type":"assistant","message":{...content blocks...},"session_id":...}
    {"type":"user","message":{...tool results...}}
    {"type":"result","subtype":"success","is_error":false,"result":"...","session_id":...,"usage":{...}}
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from coral.workspace.repo import _clean_env

logger = logging.getLogger(__name__)

# Synthetic frame type emitted once the claude process exits, so SSE
# subscribers can close their stream cleanly. Not produced by `claude`.
CLOSED_FRAME_TYPE = "_closed"


def _build_cmd(claude_bin: str, model: str | None, extra_args: list[str] | None) -> list[str]:
    cmd = [
        claude_bin,
        "--print",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    if model:
        cmd += ["--model", model]
    if extra_args:
        cmd += list(extra_args)
    return cmd


def _user_frame(text: str) -> str:
    return (
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": [{"type": "text", "text": text}]},
            }
        )
        + "\n"
    )


class ChatSession:
    """One interactive ``claude`` subprocess + a fan-out of its output frames."""

    def __init__(
        self,
        *,
        session_id: str,
        workdir: Path,
        model: str | None = None,
        extra_args: list[str] | None = None,
        env: dict[str, str] | None = None,
        claude_bin: str = "claude",
    ) -> None:
        self.session_id = session_id
        self.workdir = Path(workdir)
        self.model = model
        self._extra_args = extra_args
        self._env = env
        self._claude_bin = claude_bin

        self.process: subprocess.Popen[str] | None = None
        # claude's own session id (from the system/init frame) — distinct from
        # our session_id; needed later for --resume.
        self.claude_session_id: str | None = None
        self.stderr_path: Path | None = None

        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._transcript: list[dict[str, Any]] = []
        self._lock = threading.Lock()  # guards subscribers + transcript
        self._stdin_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._stderr_file: Any = None

    def start(self) -> None:
        """Spawn the subprocess and begin reading its stdout.

        Must be called from within a running asyncio loop (a web handler or
        ``asyncio.run``) — the reader thread bridges frames back onto that
        loop via ``call_soon_threadsafe``.
        """
        if self.process is not None:
            raise RuntimeError("session already started")
        self._loop = asyncio.get_running_loop()

        cmd = _build_cmd(self._claude_bin, self.model, self._extra_args)
        env = self._env if self._env is not None else _clean_env()

        # stderr → a file (not a pipe) so a chatty claude can never deadlock on
        # a full, undrained stderr pipe. Mirrors claude_code.py's err split.
        self.stderr_path = Path(tempfile.gettempdir()) / f"coral-chat-{self.session_id}.err"
        self._stderr_file = open(self.stderr_path, "w", buffering=1)

        logger.info("chat %s: spawning %s in %s", self.session_id, " ".join(cmd), self.workdir)
        self.process = subprocess.Popen(
            cmd,
            cwd=str(self.workdir),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_file,
            start_new_session=True,  # own process group for clean group-kill
            env=env,
            bufsize=1,  # line-buffered
            text=True,
        )
        self._reader = threading.Thread(
            target=self._read_stdout, name=f"chat-{self.session_id}", daemon=True
        )
        self._reader.start()

    @property
    def alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def send(self, text: str) -> None:
        """Write one user message frame to the subprocess stdin."""
        proc = self.process
        if proc is None or proc.poll() is not None or proc.stdin is None:
            raise RuntimeError("session not running")
        with self._stdin_lock:
            proc.stdin.write(_user_frame(text))
            proc.stdin.flush()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Return a queue fed every frame; replays the transcript so far."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        with self._lock:
            for frame in self._transcript:
                q.put_nowait(frame)
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    # ── internals ────────────────────────────────────────────────────────

    def _emit(self, frame: dict[str, Any]) -> None:
        """Record a frame and fan it out to subscribers (reader-thread side)."""
        with self._lock:
            self._transcript.append(frame)
            subs = list(self._subscribers)
        loop = self._loop
        if loop is None:
            return
        for q in subs:
            loop.call_soon_threadsafe(self._safe_put, q, frame)

    @staticmethod
    def _safe_put(q: asyncio.Queue[dict[str, Any]], frame: dict[str, Any]) -> None:
        try:
            q.put_nowait(frame)
        except asyncio.QueueFull:
            pass

    def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            for line in self.process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    frame = json.loads(line)
                except json.JSONDecodeError:
                    frame = {"type": "_raw", "line": line}
                if not isinstance(frame, dict):
                    frame = {"type": "_raw", "value": frame}
                if frame.get("type") == "system" and frame.get("subtype") == "init":
                    sid = frame.get("session_id")
                    if isinstance(sid, str):
                        self.claude_session_id = sid
                self._emit(frame)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("chat %s: stdout reader error: %s", self.session_id, e)
        finally:
            self._emit({"type": CLOSED_FRAME_TYPE, "session_id": self.session_id})

    def stop(self) -> None:
        """Close stdin and tear down the process group + reader thread."""
        proc = self.process
        if proc is not None:
            try:
                if proc.stdin and not proc.stdin.closed:
                    proc.stdin.close()
            except Exception:
                pass
            if proc.poll() is None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        proc.kill()
                    proc.wait(timeout=5)
        if self._reader is not None:
            self._reader.join(timeout=5)
        if self._stderr_file is not None:
            try:
                self._stderr_file.close()
            except Exception:
                pass
            self._stderr_file = None


class ChatSessionManager:
    """In-memory registry of live chat sessions, keyed by our session id."""

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._lock = threading.Lock()

    def create(
        self,
        *,
        workdir: Path,
        model: str | None = None,
        extra_args: list[str] | None = None,
        env: dict[str, str] | None = None,
        claude_bin: str = "claude",
    ) -> ChatSession:
        """Create, start, and register a session. Call from an async context."""
        session_id = uuid.uuid4().hex
        session = ChatSession(
            session_id=session_id,
            workdir=workdir,
            model=model,
            extra_args=extra_args,
            env=env,
            claude_bin=claude_bin,
        )
        session.start()
        with self._lock:
            self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> ChatSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def close(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        session.stop()
        return True

    def shutdown(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.stop()
