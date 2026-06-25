"""Chat routes — scaffold a workspace, start a session, stream frames over SSE.

P1+P2 of the chat module (``design/chat-module.md``). Workspaces are
path-gated via ``coral.chat.workspace.validate_local_path`` and new tasks
scaffolded via ``coral init``. The ``coral start`` approval hook is P3.
"""

from __future__ import annotations

import asyncio
import json

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from coral.chat.session import CLOSED_FRAME_TYPE, ChatSessionManager
from coral.chat.workspace import LocalPathError, scaffold_task, validate_local_path

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _manager(request: Request) -> ChatSessionManager:
    return request.app.state.chat_manager


async def post_chat_session(request: Request) -> Response:
    """POST /api/chat/sessions {workdir, model?} → {session_id}."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    workdir = body.get("workdir")
    if not workdir:
        return JSONResponse({"error": "workdir is required"}, status_code=400)
    try:
        wd = validate_local_path(workdir)
    except LocalPathError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    session = _manager(request).create(workdir=wd, model=body.get("model"))
    return JSONResponse({"session_id": session.session_id, "workdir": str(wd)})


async def post_chat_workspace(request: Request) -> Response:
    """POST /api/chat/workspaces {parent, name} → scaffold a task via `coral init`."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    parent = body.get("parent")
    name = body.get("name")
    if not parent or not name:
        return JSONResponse({"error": "parent and name are required"}, status_code=400)
    try:
        # scaffold_task runs `coral init` (subprocess) — keep it off the loop.
        dest = await asyncio.get_running_loop().run_in_executor(None, scaffold_task, parent, name)
    except LocalPathError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"workdir": str(dest)})


async def post_chat_message(request: Request) -> Response:
    """POST /api/chat/{sid}/message {text} → enqueue onto the session stdin."""
    session = _manager(request).get(request.path_params["sid"])
    if session is None:
        return JSONResponse({"error": "no such session"}, status_code=404)
    if not session.alive:
        return JSONResponse({"error": "session not running"}, status_code=409)
    try:
        body = await request.json()
    except Exception:
        body = {}
    text = body.get("text", "")
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)
    session.send(text)
    return JSONResponse({"ok": True})


async def chat_events(request: Request) -> Response:
    """GET /api/chat/{sid}/events — SSE stream of the session's frames."""
    session = _manager(request).get(request.path_params["sid"])
    if session is None:
        return JSONResponse({"error": "no such session"}, status_code=404)
    queue = session.subscribe()

    async def event_generator():
        try:
            yield f"event: connected\ndata: {json.dumps({'session_id': session.session_id})}\n\n"
            while True:
                try:
                    frame = await asyncio.wait_for(queue.get(), timeout=1.0)
                except TimeoutError:
                    if await request.is_disconnected():
                        break
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: frame\ndata: {json.dumps(frame)}\n\n"
                if frame.get("type") == CLOSED_FRAME_TYPE:
                    break
                if await request.is_disconnected():
                    break
        finally:
            session.unsubscribe(queue)

    return StreamingResponse(
        event_generator(), media_type="text/event-stream", headers=_SSE_HEADERS
    )


async def delete_chat_session(request: Request) -> Response:
    """DELETE /api/chat/{sid} — stop the session."""
    sid = request.path_params["sid"]
    manager = _manager(request)
    # close() kills a process group + joins the reader thread; keep that off
    # the event loop so a slow teardown can't stall other requests.
    ok = await asyncio.get_running_loop().run_in_executor(None, manager.close, sid)
    return JSONResponse({"closed": ok}, status_code=200 if ok else 404)
