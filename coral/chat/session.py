"""Interactive chat session — a per-runtime bridge over an agent CLI.

Drives one of the chat adapters (``coral.chat.adapters``). Two lifecycles:

  - ``streaming`` (claude_code): one long-lived process; ``send()`` writes a
    user frame to stdin; a reader thread streams output frames continuously
    until the process exits (then a synthetic ``_closed`` frame is emitted).
  - ``per_turn`` (codex, opencode): ``start()`` spawns nothing; each
    ``send()`` spawns a fresh process for that turn, streams its output to
    completion, and exits — context carries over via session-resume. The
    session stays alive between turns; ``_closed`` is emitted on ``stop()``.

The adapter normalizes each runtime's events into the common (claude-shaped)
frame schema, so the web UI renders all runtimes uniformly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from coral.chat.adapters import PER_TURN, STREAMING, ChatAdapter, get_adapter
from coral.chat.transcript import ChatTranscript
from coral.workspace.repo import _clean_env

logger = logging.getLogger(__name__)

# Synthetic frame type emitted once a session ends, so SSE subscribers can
# close their stream cleanly. Not produced by any CLI.
CLOSED_FRAME_TYPE = "_closed"


class ChatSession:
    """One chat session (a CLI bridge) + a fan-out of normalized output frames."""

    def __init__(
        self,
        *,
        session_id: str,
        workdir: Path,
        adapter: ChatAdapter,
        model: str | None = None,
        extra_args: list[str] | None = None,
        env: dict[str, str] | None = None,
        approval: dict[str, str] | None = None,
        transcript_root: Path | None = None,
        binary: str | None = None,
    ) -> None:
        self.session_id = session_id
        self.workdir = Path(workdir)
        self.model = model
        self._adapter = adapter
        self.runtime = adapter.runtime
        # argv[0] for spawned commands; overridable for tests.
        self._binary = binary or adapter.binary
        self._extra_args = extra_args
        self._env = env
        # The PreToolUse `coral start` gate is claude/streaming-only (decision A).
        self._approval = approval if adapter.mode == STREAMING else None
        self._transcript_root = transcript_root
        self._writer: ChatTranscript | None = None

        # streaming: the long-lived process. per_turn: the in-flight turn.
        self.process: subprocess.Popen[str] | None = None
        self._turn_proc: subprocess.Popen[str] | None = None
        self._turn_thread: threading.Thread | None = None
        # the runtime's own session/thread id, for resume continuity.
        self.runtime_session_id: str | None = None
        self.stderr_path: Path | None = None
        self._env_resolved: dict[str, str] | None = None

        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._transcript: list[dict[str, Any]] = []
        self._lock = threading.Lock()  # guards subscribers + transcript
        self._stdin_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._stderr_file: Any = None
        self._started = False
        self._stopped = False
        self._closed = False

    def start(self) -> None:
        """Begin the session. Must be called from within a running asyncio loop."""
        if self._started:
            raise RuntimeError("session already started")
        self._started = True
        self._loop = asyncio.get_running_loop()

        if self._transcript_root is not None:
            self._writer = ChatTranscript(self.session_id, self._transcript_root)
            self._writer.open(
                {"workdir": str(self.workdir), "model": self.model, "runtime": self.runtime}
            )

        # stderr → a file (not a pipe) so a chatty CLI can never deadlock on a
        # full, undrained stderr pipe. Reused across turns in per_turn mode.
        self.stderr_path = Path(tempfile.gettempdir()) / f"coral-chat-{self.session_id}.err"
        self._stderr_file = open(self.stderr_path, "w", buffering=1)

        base_env = dict(self._env) if self._env is not None else _clean_env()

        if self._adapter.mode == STREAMING:
            self._start_streaming(base_env)
        else:
            self._env_resolved = base_env
            # No process yet; surface a synthetic init so the UI shows the session.
            self._emit(
                {
                    "type": "system",
                    "subtype": "init",
                    "model": self.model,
                    "cwd": str(self.workdir),
                    "runtime": self.runtime,
                }
            )

    def _start_streaming(self, env: dict[str, str]) -> None:
        settings_json: str | None = None
        if self._approval and self._approval.get("base_url"):
            hook_path = Path(__file__).resolve().parent.parent / "hooks" / "pretooluse_gate.py"
            settings = {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Write|Edit|MultiEdit|Bash",
                            "hooks": [
                                {"type": "command", "command": f"{sys.executable} {hook_path}"}
                            ],
                        }
                    ]
                }
            }
            settings_json = json.dumps(settings)
            env["CORAL_CHAT_CALLBACK_URL"] = self._approval["base_url"]
            env["CORAL_CHAT_CALLBACK_TOKEN"] = self._approval.get("token", "")
            env["CORAL_CHAT_SESSION_ID"] = self.session_id
            env["CORAL_CHAT_GATE_MODE"] = self._approval.get("gate_mode", "bypass")

        cmd = self._adapter.build_streaming_command(
            self._binary, self.model, self._extra_args, settings_json
        )
        logger.info("chat %s: spawning %s in %s", self.session_id, " ".join(cmd), self.workdir)
        self.process = subprocess.Popen(
            cmd,
            cwd=str(self.workdir),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_file,
            start_new_session=True,
            env=env,
            bufsize=1,
            text=True,
        )
        self._reader = threading.Thread(
            target=self._read_stream, name=f"chat-{self.session_id}", daemon=True
        )
        self._reader.start()

    @property
    def alive(self) -> bool:
        if self._adapter.mode == STREAMING:
            return self.process is not None and self.process.poll() is None
        return not self._closed

    def send(self, text: str) -> None:
        """Deliver a user message — write to stdin (streaming) or spawn a turn."""
        if self._adapter.mode == STREAMING:
            proc = self.process
            if proc is None or proc.poll() is not None or proc.stdin is None:
                raise RuntimeError("session not running")
            with self._stdin_lock:
                proc.stdin.write(self._adapter.encode_user_message(text))
                proc.stdin.flush()
        else:
            self._send_per_turn(text)

    def _send_per_turn(self, text: str) -> None:
        if self._closed:
            raise RuntimeError("session closed")
        if self._turn_thread is not None and self._turn_thread.is_alive():
            raise RuntimeError("a turn is already in progress")
        cmd = self._adapter.build_turn_command(
            self._binary, self.model, text, self.runtime_session_id, self._extra_args
        )
        logger.info("chat %s: turn %s in %s", self.session_id, " ".join(cmd), self.workdir)
        proc = subprocess.Popen(
            cmd,
            cwd=str(self.workdir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=self._stderr_file,
            start_new_session=True,
            env=self._env_resolved,
            bufsize=1,
            text=True,
        )
        self._turn_proc = proc
        self._turn_thread = threading.Thread(
            target=self._read_turn, args=(proc,), name=f"chat-turn-{self.session_id}", daemon=True
        )
        self._turn_thread.start()

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

    def emit_event(self, frame: dict[str, Any]) -> None:
        """Inject a synthetic frame (e.g. awaiting_approval) into the stream."""
        self._emit(frame)

    # ── internals ────────────────────────────────────────────────────────

    def _emit(self, frame: dict[str, Any]) -> None:
        with self._lock:
            self._transcript.append(frame)
            if self._writer is not None:
                self._writer.append(frame)
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

    def _normalize_line(self, line: str) -> dict[str, Any] | None:
        line = line.strip()
        if not line:
            return None
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return {"type": "_raw", "line": line}
        if not isinstance(obj, dict):
            return {"type": "_raw", "value": obj}
        sid = self._adapter.session_id_from(obj)
        if sid:
            self.runtime_session_id = sid
        return self._adapter.normalize(obj)

    def _read_stream(self) -> None:
        """Streaming mode: read the long-lived process until EOF."""
        assert self.process is not None and self.process.stdout is not None
        try:
            for line in self.process.stdout:
                frame = self._normalize_line(line)
                if frame is not None:
                    self._emit(frame)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("chat %s: stream reader error: %s", self.session_id, e)
        finally:
            self._closed = True
            self._emit({"type": CLOSED_FRAME_TYPE, "session_id": self.session_id})

    def _read_turn(self, proc: subprocess.Popen[str]) -> None:
        """Per-turn mode: read one turn's process to completion (no _closed)."""
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                frame = self._normalize_line(line)
                if frame is not None:
                    self._emit(frame)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("chat %s: turn reader error: %s", self.session_id, e)
        finally:
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
            if self._turn_proc is proc:
                self._turn_proc = None

    @staticmethod
    def _kill_proc(proc: subprocess.Popen[str] | None) -> None:
        if proc is None:
            return
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

    def stop(self) -> None:
        """Tear down the session: kill any process(es), join readers, close out."""
        if self._stopped:
            return
        self._stopped = True
        self._closed = True
        self._kill_proc(self.process)
        self._kill_proc(self._turn_proc)
        for th in (self._reader, self._turn_thread):
            if th is not None:
                th.join(timeout=5)
        if self._stderr_file is not None:
            try:
                self._stderr_file.close()
            except Exception:
                pass
            self._stderr_file = None
        # Streaming emits _closed from its reader's EOF; per_turn has no
        # persistent reader, so emit it here.
        if self._adapter.mode == PER_TURN:
            self._emit({"type": CLOSED_FRAME_TYPE, "session_id": self.session_id})
        if self._writer is not None:
            self._writer.close()


class ChatSessionManager:
    """In-memory registry of live chat sessions, keyed by our session id."""

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._lock = threading.Lock()

    def create(
        self,
        *,
        workdir: Path,
        runtime: str = "claude_code",
        model: str | None = None,
        extra_args: list[str] | None = None,
        env: dict[str, str] | None = None,
        approval: dict[str, str] | None = None,
        transcript_root: Path | None = None,
        binary: str | None = None,
    ) -> ChatSession:
        """Create, start, and register a session. Call from an async context."""
        adapter = get_adapter(runtime)
        session_id = uuid.uuid4().hex
        session = ChatSession(
            session_id=session_id,
            workdir=workdir,
            adapter=adapter,
            model=model,
            extra_args=extra_args,
            env=env,
            approval=approval,
            transcript_root=transcript_root,
            binary=binary,
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
