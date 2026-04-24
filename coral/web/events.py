"""SSE (Server-Sent Events) endpoint with file-system watcher."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from starlette.requests import Request
from starlette.responses import StreamingResponse


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
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = subscribers if subscribers is not None else []
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
        attempts_dir = self.coral_dir / "public" / "attempts"
        if attempts_dir.exists():
            files = list(attempts_dir.glob("*.json"))
            state["attempts_count"] = len(files)
            state["attempts_mtime"] = max(
                (f.stat().st_mtime for f in files), default=0
            )
        else:
            state["attempts_count"] = 0
            state["attempts_mtime"] = 0

        # Notes: mtime
        notes_file = self.coral_dir / "public" / "notes" / "notes.md"
        if notes_file.exists():
            state["notes_mtime"] = notes_file.stat().st_mtime
        else:
            state["notes_mtime"] = 0

        # Logs: per-file sizes
        logs_dir = self.coral_dir / "public" / "logs"
        log_sizes: dict[str, int] = {}
        if logs_dir.exists():
            for lf in logs_dir.glob("*.log"):
                log_sizes[lf.name] = lf.stat().st_size
        state["log_sizes"] = log_sizes

        # Eval count
        eval_count_file = self.coral_dir / "public" / "eval_count"
        if eval_count_file.exists():
            try:
                state["eval_count"] = int(eval_count_file.read_text().strip())
            except ValueError:
                state["eval_count"] = 0
        else:
            state["eval_count"] = 0

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
                self._broadcast({
                    "event": "attempt:new",
                    "data": {
                        "count": new_state["attempts_count"],
                        "previous": self._state.get("attempts_count", 0),
                    },
                })

            if new_state["attempts_mtime"] > self._state.get("attempts_mtime", 0):
                self._broadcast({
                    "event": "attempt:update",
                    "data": {"mtime": new_state["attempts_mtime"]},
                })

            if new_state["notes_mtime"] > self._state.get("notes_mtime", 0):
                self._broadcast({
                    "event": "note:update",
                    "data": {"mtime": new_state["notes_mtime"]},
                })

            # Check log file growth
            old_sizes = self._state.get("log_sizes", {})
            for name, size in new_state["log_sizes"].items():
                old_size = old_sizes.get(name, 0)
                if size > old_size:
                    self._broadcast({
                        "event": "log:update",
                        "data": {"file": name, "size": size, "delta": size - old_size},
                    })

            if new_state["eval_count"] != self._state.get("eval_count", 0):
                self._broadcast({
                    "event": "eval:update",
                    "data": {"count": new_state["eval_count"]},
                })

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
                except asyncio.TimeoutError:
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
