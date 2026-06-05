"""SSE (Server-Sent Events) endpoint with file-system watcher."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import StreamingResponse

from coral.hub._island import all_view_roots
from coral.hub.attempts import read_eval_count


class FileWatcher:
    """Watches .coral/ directory for changes and broadcasts SSE events."""

    def __init__(
        self,
        coral_dir: Path,
        poll_interval: float = 2.0,
        subscribers: list[asyncio.Queue[dict[str, Any]]] | None = None,
    ):
        self.coral_dir = coral_dir
        self.poll_interval = poll_interval
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = (
            subscribers if subscribers is not None else []
        )
        self._state: dict[str, Any] = {}
        self._running = False

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def _broadcast(self, event: dict[str, Any]) -> None:
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def _snapshot(self) -> dict[str, Any]:
        """Take a snapshot of the .coral/ directory state."""
        state: dict[str, Any] = {}

        # Attempts: count + latest mtime
        attempt_files: list[Path] = []
        for view_root in all_view_roots(self.coral_dir):
            attempts_dir = view_root / "attempts"
            if attempts_dir.exists():
                attempt_files.extend(attempts_dir.glob("*.json"))
        state["attempts_count"] = len(attempt_files)
        state["attempts_mtime"] = max((f.stat().st_mtime for f in attempt_files), default=0)

        # Notes: mtime
        note_files: list[Path] = []
        for view_root in all_view_roots(self.coral_dir):
            notes_dir = view_root / "notes"
            if notes_dir.exists():
                note_files.extend(notes_dir.rglob("*.md"))
        state["notes_mtime"] = max((f.stat().st_mtime for f in note_files), default=0)

        # Logs: per-file sizes
        log_sizes: dict[str, int] = {}
        is_multi = (self.coral_dir / "islands").exists()
        for view_root in all_view_roots(self.coral_dir):
            logs_dir = view_root / "logs"
            if not logs_dir.exists():
                continue
            for lf in logs_dir.glob("*.log"):
                key = f"{view_root.name}/{lf.name}" if is_multi else lf.name
                log_sizes[key] = lf.stat().st_size
        state["log_sizes"] = log_sizes

        # Eval count
        state["eval_count"] = read_eval_count(self.coral_dir)

        return state

    async def run(self) -> None:
        """Main polling loop. Call as an asyncio task."""
        self._running = True
        self._state = self._snapshot()

        while self._running:
            await asyncio.sleep(self.poll_interval)

            new_state = self._snapshot()

            # Detect changes
            if new_state["attempts_count"] > self._state.get("attempts_count", 0):
                self._broadcast(
                    {
                        "event": "attempt:new",
                        "data": {
                            "count": new_state["attempts_count"],
                            "previous": self._state.get("attempts_count", 0),
                        },
                    }
                )

            if new_state["attempts_mtime"] > self._state.get("attempts_mtime", 0):
                self._broadcast(
                    {
                        "event": "attempt:update",
                        "data": {"mtime": new_state["attempts_mtime"]},
                    }
                )

            if new_state["notes_mtime"] > self._state.get("notes_mtime", 0):
                self._broadcast(
                    {
                        "event": "note:update",
                        "data": {"mtime": new_state["notes_mtime"]},
                    }
                )

            # Check log file growth
            old_sizes = self._state.get("log_sizes", {})
            for name, size in new_state["log_sizes"].items():
                old_size = old_sizes.get(name, 0)
                if size > old_size:
                    self._broadcast(
                        {
                            "event": "log:update",
                            "data": {"file": name, "size": size, "delta": size - old_size},
                        }
                    )

            if new_state["eval_count"] != self._state.get("eval_count", 0):
                self._broadcast(
                    {
                        "event": "eval:update",
                        "data": {"count": new_state["eval_count"]},
                    }
                )

            self._state = new_state

    def stop(self) -> None:
        self._running = False


async def sse_endpoint(request: Request) -> StreamingResponse:
    """GET /api/events — Server-Sent Events stream."""
    watcher: FileWatcher = request.app.state.watcher

    queue = watcher.subscribe()

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Send initial connected event
            yield f"event: connected\ndata: {json.dumps({'status': 'ok'})}\n\n"

            heartbeat_interval = 15.0
            last_heartbeat = time.time()

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    event_type = event.get("event", "message")
                    data = json.dumps(event.get("data", {}))
                    yield f"event: {event_type}\ndata: {data}\n\n"
                except TimeoutError:
                    # Send heartbeat if enough time has passed
                    now = time.time()
                    if now - last_heartbeat >= heartbeat_interval:
                        yield f"event: heartbeat\ndata: {json.dumps({'time': now})}\n\n"
                        last_heartbeat = now

                # Check if client disconnected
                if await request.is_disconnected():
                    break
        finally:
            watcher.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
