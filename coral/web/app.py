"""Starlette application factory for the CORAL web dashboard."""

from __future__ import annotations

import asyncio
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from coral.web.api import (
    get_agent_attempts,
    get_attempt_detail,
    get_attempts,
    get_config,
    get_notes,
    get_leaderboard,
    get_logs,
    get_logs_list,
    get_runs,
    get_skill_detail,
    get_skills,
    get_status,
    switch_run,
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

    async def on_startup() -> None:
        app.state.coral_dir = coral_dir
        app.state.results_dir = results_dir
        app.state._switch_lock = asyncio.Lock()
        app.state.watcher = FileWatcher(coral_dir)
        app.state._watcher_task = asyncio.create_task(app.state.watcher.run())

    async def on_shutdown() -> None:
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
        Route("/api/notes", get_notes),
        Route("/api/skills", get_skills),
        Route("/api/skills/{name}", get_skill_detail),
        Route("/api/logs", get_logs_list),
        Route("/api/logs/{agent_id}", get_logs),
        Route("/api/status", get_status),
        Route("/api/runs", get_runs),
        Route("/api/runs/switch", switch_run, methods=["POST"]),
        Route("/api/events", sse_endpoint),
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
        on_startup=[on_startup],
        on_shutdown=[on_shutdown],
    )

    return app
