"""Starlette application factory for the CORAL web dashboard."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from coral.chat.approval import ApprovalRegistry
from coral.chat.session import ChatSessionManager
from coral.web.api import (
    get_agent_attempts,
    get_attempt_detail,
    get_attempts,
    get_config,
    get_dag,
    get_leaderboard,
    get_logs,
    get_logs_list,
    get_notes,
    get_notes_graph,
    get_runs,
    get_skill_detail,
    get_skills,
    get_status,
    get_steering,
    post_steer,
    switch_run,
)
from coral.web.chat import (
    chat_events,
    delete_chat_session,
    get_chat_browse,
    get_chat_sessions,
    get_chat_transcript,
    post_chat_approval,
    post_chat_internal_approval,
    post_chat_message,
    post_chat_session,
    post_chat_workspace,
)
from coral.web.events import FileWatcher, sse_endpoint


def create_app(coral_dir: Path, results_dir: Path | None = None) -> Starlette:
    """Create the Starlette application.

    Args:
        coral_dir: Path to the .coral/ directory to serve.
        results_dir: Path to the top-level results/ directory (for run listing).
                     If not provided, derived from coral_dir.
    """
    coral_dir = Path(coral_dir).resolve()
    if results_dir is None:
        # coral_dir = results/<task>/<run>/.coral → results_dir = results/
        results_dir = coral_dir.parent.parent.parent
    results_dir = Path(results_dir).resolve()
    static_dir = Path(__file__).parent / "static"

    @asynccontextmanager
    async def lifespan(app):
        # startup
        app.state.coral_dir = coral_dir
        app.state.results_dir = results_dir
        app.state._switch_lock = asyncio.Lock()
        app.state.watcher = FileWatcher(coral_dir)
        app.state._watcher_task = asyncio.create_task(app.state.watcher.run())
        app.state.chat_manager = ChatSessionManager()
        app.state.approvals = ApprovalRegistry()
        try:
            yield
        finally:
            # shutdown
            app.state.chat_manager.shutdown()
            app.state.watcher.stop()
            app.state._watcher_task.cancel()
            try:
                await app.state._watcher_task
            except asyncio.CancelledError:
                pass

    # SPA fallback: serve index.html for any non-API, non-static route
    async def spa_fallback(request: Request) -> Response:
        index = static_dir / "index.html"
        if index.exists():
            return FileResponse(index)
        return Response("Dashboard not built. Run: cd web && npm run build", status_code=404)

    routes = [
        # API routes
        Route("/api/config", get_config),
        Route("/api/attempts", get_attempts),
        Route("/api/leaderboard", get_leaderboard),
        Route("/api/attempts/agent/{id}", get_agent_attempts),
        Route("/api/attempts/{hash}", get_attempt_detail),
        Route("/api/dag", get_dag),
        Route("/api/notes/graph", get_notes_graph),
        Route("/api/notes", get_notes),
        Route("/api/skills", get_skills),
        Route("/api/skills/{name}", get_skill_detail),
        Route("/api/logs", get_logs_list),
        Route("/api/logs/{agent_id}", get_logs),
        Route("/api/status", get_status),
        Route("/api/steer", get_steering),
        Route("/api/steer", post_steer, methods=["POST"]),
        Route("/api/runs", get_runs),
        Route("/api/runs/switch", switch_run, methods=["POST"]),
        Route("/api/events", sse_endpoint),
        # Chat module (design/chat-module.md)
        Route("/api/chat/workspaces", post_chat_workspace, methods=["POST"]),
        Route("/api/chat/browse", get_chat_browse),
        Route("/api/chat/internal/approval", post_chat_internal_approval, methods=["POST"]),
        Route("/api/chat/sessions", post_chat_session, methods=["POST"]),
        Route("/api/chat/sessions", get_chat_sessions, methods=["GET"]),
        Route("/api/chat/{sid}/approvals/{pid}", post_chat_approval, methods=["POST"]),
        Route("/api/chat/{sid}/message", post_chat_message, methods=["POST"]),
        Route("/api/chat/{sid}/transcript", get_chat_transcript),
        Route("/api/chat/{sid}/events", chat_events),
        Route("/api/chat/{sid}", delete_chat_session, methods=["DELETE"]),
    ]

    # Mount static files if the directory exists (post-build)
    if static_dir.exists():
        routes.append(
            Mount("/assets", app=StaticFiles(directory=static_dir / "assets"), name="assets")
            if (static_dir / "assets").exists()
            else Mount("/static", app=StaticFiles(directory=static_dir), name="static")
        )

    # SPA catch-all must be last
    routes.append(Route("/{path:path}", spa_fallback))

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]

    app = Starlette(
        routes=routes,
        middleware=middleware,
        lifespan=lifespan,
    )

    return app
