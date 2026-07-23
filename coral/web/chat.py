"""Chat routes — scaffold a workspace, run a session, stream/gate/persist it.

The chat module (``design/chat-module.md``): workspaces are path-gated
(``validate_local_path``) and scaffolded (``coral init``); sessions stream
over SSE; ``coral start`` is gated by the PreToolUse approval callback; and
frames are persisted (``coral.chat.transcript``) for history.
"""

from __future__ import annotations

import asyncio
import json
import uuid

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from coral.chat.adapters import canonical_runtime, supported_runtimes
from coral.chat.session import CLOSED_FRAME_TYPE, ChatSessionManager
from coral.chat.transcript import chat_home, list_sessions, read_meta, read_transcript
from coral.chat.workspace import (
    LocalPathError,
    browse_directory,
    scaffold_task,
    validate_local_path,
)

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _manager(request: Request) -> ChatSessionManager:
    return request.app.state.chat_manager


def _approval_config(request: Request) -> dict[str, str] | None:
    """Build the per-session approval config from app.state, or None.

    None disables the `coral start` gate (P1/P2 behaviour). It is populated
    by the serving layer (`coral ui`) once it knows its localhost URL + token.
    """
    base_url = getattr(request.app.state, "chat_callback_base_url", None)
    if not base_url:
        return None
    return {
        "base_url": base_url,
        "token": getattr(request.app.state, "chat_callback_token", ""),
        "gate_mode": getattr(request.app.state, "chat_gate_mode", "bypass"),
    }


def _resolve_runtime_model(body: dict) -> tuple[str, str | None]:
    """Resolve {runtime, binding, model} → (runtime, model).

    A ``binding`` (a name in ~/.config/coral/agents.yaml) supplies the runtime
    and a default model; explicit ``runtime``/``model`` override it. Defaults to
    claude_code.
    """
    runtime = body.get("runtime")
    model = body.get("model")
    binding_name = body.get("binding")
    if binding_name:
        try:
            from coral.user_agents import load_store

            b = load_store().get(binding_name)
        except Exception:
            b = None
        if b is not None:
            runtime = runtime or b.runtime
            if not model:
                model = b.model or None
    return (runtime or "claude_code"), (model or None)


async def post_chat_session(request: Request) -> Response:
    """POST /api/chat/sessions {workdir, runtime?, binding?, model?} → {session_id}."""
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

    runtime, model = _resolve_runtime_model(body)
    # The `coral start` approval gate is claude/streaming-only (decision A).
    approval = _approval_config(request) if canonical_runtime(runtime) == "claude_code" else None
    try:
        session = _manager(request).create(
            workdir=wd, runtime=runtime, model=model, approval=approval, transcript_root=chat_home()
        )
    except ValueError as e:  # unsupported runtime
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(
        {"session_id": session.session_id, "workdir": str(wd), "runtime": session.runtime}
    )


async def get_chat_bindings(request: Request) -> Response:
    """GET /api/chat/bindings — chat-capable bindings + supported runtimes."""
    bindings: list[dict] = []
    default = None
    try:
        from coral.user_agents import load_store

        store = load_store()
        default = store.default
        bindings = [
            {"name": b.name, "runtime": b.runtime, "model": b.model}
            for b in store.bindings.values()
            if canonical_runtime(b.runtime) in supported_runtimes()
        ]
    except Exception:
        pass
    return JSONResponse(
        {"bindings": bindings, "default": default, "runtimes": supported_runtimes()}
    )


async def get_chat_browse(request: Request) -> Response:
    """GET /api/chat/browse?path=… — list sub-directories for the UI picker."""
    try:
        return JSONResponse(browse_directory(request.query_params.get("path")))
    except LocalPathError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


async def get_chat_sessions(request: Request) -> Response:
    """GET /api/chat/sessions — list persisted chat sessions (newest first)."""
    return JSONResponse({"sessions": list_sessions()})


async def get_chat_transcript(request: Request) -> Response:
    """GET /api/chat/{sid}/transcript — frames + meta for a session, from disk."""
    sid = request.path_params["sid"]
    return JSONResponse({"session_id": sid, "meta": read_meta(sid), "frames": read_transcript(sid)})


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
    if session.busy():
        return JSONResponse({"error": "a turn is already in progress"}, status_code=409)
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


async def post_chat_internal_approval(request: Request) -> Response:
    """POST /api/chat/internal/approval — the PreToolUse hook's callback.

    Token-gated (localhost only). Parks the request until the user resolves it
    in the UI, then returns ``{"decision": "allow"|"deny"}``.
    """
    expected = getattr(request.app.state, "chat_callback_token", None)
    if not expected or request.headers.get("X-Coral-Callback-Token", "") != expected:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    session_id = body.get("session_id", "")
    prompt_id = body.get("prompt_id") or uuid.uuid4().hex
    tool_name = body.get("tool_name", "")
    tool_input = body.get("tool_input", {}) or {}

    registry = request.app.state.approvals
    # Register the pending future BEFORE surfacing the prompt, so a fast UI
    # resolve can't race ahead of registration.
    registry.create(
        prompt_id,
        {"session_id": session_id, "tool_name": tool_name, "tool_input": tool_input},
    )
    session = _manager(request).get(session_id)
    if session is not None:
        session.emit_event(
            {
                "type": "awaiting_approval",
                "prompt_id": prompt_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
            }
        )
    decision = await registry.wait(prompt_id, timeout=300)
    if session is not None:
        session.emit_event(
            {"type": "approval_resolved", "prompt_id": prompt_id, "decision": decision}
        )
    return JSONResponse({"decision": decision})


async def post_chat_approval(request: Request) -> Response:
    """POST /api/chat/{sid}/approvals/{pid} {decision} — UI resolves an approval."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    decision = body.get("decision", "deny")
    if decision not in ("allow", "deny"):
        return JSONResponse({"error": "decision must be allow|deny"}, status_code=400)
    ok = request.app.state.approvals.resolve(request.path_params["pid"], decision)
    return JSONResponse({"resolved": ok}, status_code=200 if ok else 404)
