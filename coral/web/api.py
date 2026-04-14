"""REST API endpoints for the CORAL web dashboard."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from starlette.requests import Request
from starlette.responses import JSONResponse

from coral.cli._helpers import is_docker_run_alive


def _coral_dir(request: Request) -> Path:
    return request.app.state.coral_dir


async def get_config(request: Request) -> JSONResponse:
    """GET /api/config — return the run configuration."""
    config_path = _coral_dir(request) / "config.yaml"
    if not config_path.exists():
        return JSONResponse({"error": "config.yaml not found"}, status_code=404)

    with open(config_path) as f:
        config = yaml.safe_load(f)
    return JSONResponse(config)


async def get_attempts(request: Request) -> JSONResponse:
    """GET /api/attempts — return all attempts sorted by timestamp."""
    from coral.hub.attempts import read_attempts

    attempts = read_attempts(str(_coral_dir(request)))
    attempts.sort(key=lambda a: a.timestamp)
    return JSONResponse([a.to_dict() for a in attempts])


async def get_leaderboard(request: Request) -> JSONResponse:
    """GET /api/leaderboard?top=N — return top N attempts by score."""
    from coral.hub.attempts import get_leaderboard as _get_leaderboard

    top_n = int(request.query_params.get("top", "20"))
    attempts = _get_leaderboard(str(_coral_dir(request)), top_n=top_n, direction=_direction(request))
    return JSONResponse([a.to_dict() for a in attempts])


async def get_attempt_detail(request: Request) -> JSONResponse:
    """GET /api/attempts/{hash} — return a single attempt."""
    commit_hash = request.path_params["hash"]
    coral_dir = _coral_dir(request)
    attempt_file = coral_dir / "public" / "attempts" / f"{commit_hash}.json"

    if not attempt_file.exists():
        # Try prefix match
        matches = list((coral_dir / "public" / "attempts").glob(f"{commit_hash}*.json"))
        if len(matches) == 1:
            attempt_file = matches[0]
        else:
            return JSONResponse({"error": "attempt not found"}, status_code=404)

    data = json.loads(attempt_file.read_text())
    return JSONResponse(data)


async def get_agent_attempts(request: Request) -> JSONResponse:
    """GET /api/attempts/agent/{id} — return attempts for a specific agent."""
    from coral.hub.attempts import get_agent_attempts as _get_agent_attempts

    agent_id = request.path_params["id"]
    attempts = _get_agent_attempts(str(_coral_dir(request)), agent_id)
    return JSONResponse([a.to_dict() for a in attempts])


async def get_notes(request: Request) -> JSONResponse:
    """GET /api/notes — return all notes."""
    from coral.hub.notes import list_notes

    entries = list_notes(str(_coral_dir(request)))
    for i, entry in enumerate(entries):
        entry["index"] = i
    return JSONResponse(entries)


async def get_skills(request: Request) -> JSONResponse:
    """GET /api/skills — return all skills."""
    from coral.hub.skills import list_skills

    skills = list_skills(str(_coral_dir(request)))
    # Convert any non-string values (e.g. datetime from YAML) to strings
    for sk in skills:
        for key in ("created", "updated"):
            if sk.get(key) and not isinstance(sk[key], str):
                sk[key] = str(sk[key])
    return JSONResponse(skills)


async def get_skill_detail(request: Request) -> JSONResponse:
    """GET /api/skills/{name} — return a specific skill."""
    from coral.hub.skills import read_skill

    name = request.path_params["name"]
    skill_dir = _coral_dir(request) / "public" / "skills" / name
    if not skill_dir.is_dir():
        return JSONResponse({"error": "skill not found"}, status_code=404)

    info = read_skill(skill_dir)
    return JSONResponse(info)


async def get_logs(request: Request) -> JSONResponse:
    """GET /api/logs/{agent_id} — return parsed log turns for an agent."""
    from coral.web.logs import list_log_files, parse_log_file

    agent_id = request.path_params["agent_id"]
    coral_dir = _coral_dir(request)
    agent_logs = list_log_files(coral_dir)

    if agent_id not in agent_logs:
        return JSONResponse({"error": "agent not found"}, status_code=404)

    # Parse all log files for this agent, grouped by session
    sessions: list[dict[str, Any]] = []
    all_session_metas: list[dict[str, Any]] = []
    global_turn_idx = 0
    for log_info in sorted(agent_logs[agent_id], key=lambda x: x["index"]):
        turns, _, session_meta = parse_log_file(Path(log_info["path"]))
        session_turns = []
        for t in turns:
            td = t.to_dict()
            td["index"] = global_turn_idx
            global_turn_idx += 1
            session_turns.append(td)
        session_data: dict[str, Any] = {
            "session_index": log_info["index"],
            "turns": session_turns,
        }
        if session_meta:
            session_data["meta"] = session_meta.to_dict()
            all_session_metas.append(session_meta.to_dict())
        sessions.append(session_data)

    # Also flatten for backward compat
    all_turns = [t for s in sessions for t in s["turns"]]

    # Aggregate session-level metadata for the whole agent
    agent_meta: dict[str, Any] | None = None
    if all_session_metas:
        total_cost = sum(m.get("total_cost_usd") or 0 for m in all_session_metas)
        total_duration = sum(m.get("duration_ms") or 0 for m in all_session_metas)
        total_api_duration = sum(m.get("duration_api_ms") or 0 for m in all_session_metas)
        total_turns = sum(m.get("num_turns") or 0 for m in all_session_metas)
        # Aggregate usage across sessions
        agg_usage: dict[str, int] = {}
        for m in all_session_metas:
            for k, v in m.get("usage", {}).items():
                if isinstance(v, (int, float)):
                    agg_usage[k] = agg_usage.get(k, 0) + int(v)
        agent_meta = {
            "total_cost_usd": total_cost,
            "duration_ms": total_duration,
            "duration_api_ms": total_api_duration,
            "num_turns": total_turns,
            "usage": agg_usage,
        }

    return JSONResponse({
        "agent_id": agent_id,
        "log_files": agent_logs[agent_id],
        "turns": all_turns,
        "sessions": sessions,
        "agent_meta": agent_meta,
    })


async def get_logs_list(request: Request) -> JSONResponse:
    """GET /api/logs — return available agents and their log files."""
    from coral.web.logs import list_log_files

    agent_logs = list_log_files(_coral_dir(request))
    return JSONResponse(agent_logs)


def _direction(request: Request) -> str:
    """Read grader direction from config. Returns 'maximize' or 'minimize'."""
    config_path = _coral_dir(request) / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        return (config.get("grader") or {}).get("direction", "maximize")
    return "maximize"


def _results_dir(request: Request) -> Path:
    return request.app.state.results_dir


def _enumerate_runs(results_dir: Path, current_coral_dir: Path) -> dict:
    """Walk results_dir and return structured task/run listing."""
    current_resolved = current_coral_dir.resolve()
    current_task = current_resolved.parent.parent.name
    current_run = current_resolved.parent.name

    tasks = []
    if not results_dir.is_dir():
        return {"current": {"task": current_task, "run": current_run}, "tasks": tasks}

    for task_dir in sorted(results_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        task_slug = task_dir.name

        # Resolve "latest" symlink target
        latest_link = task_dir / "latest"
        latest_target = None
        if latest_link.is_symlink():
            try:
                latest_target = latest_link.resolve()
            except OSError:
                pass

        runs = []
        for run_dir in sorted(task_dir.iterdir(), reverse=True):
            if not run_dir.is_dir() or run_dir.is_symlink():
                continue
            coral_dir = run_dir / ".coral"
            if not coral_dir.is_dir():
                continue

            # Check manager status
            pid_file = coral_dir / "public" / "manager.pid"
            status = "stopped"
            if pid_file.exists():
                try:
                    pid = int(pid_file.read_text().strip())
                    os.kill(pid, 0)
                    status = "running"
                except (ProcessLookupError, PermissionError, ValueError):
                    pass
            if status == "stopped" and is_docker_run_alive(coral_dir):
                status = "running"

            # Count attempts
            attempts_dir = coral_dir / "public" / "attempts"
            attempt_count = len(list(attempts_dir.glob("*.json"))) if attempts_dir.exists() else 0

            # Check if latest (latest symlink now points to run_dir, not .coral)
            is_latest = latest_target is not None and latest_target == run_dir.resolve()

            runs.append({
                "timestamp": run_dir.name,
                "status": status,
                "attempts": attempt_count,
                "is_latest": is_latest,
            })

        if runs:
            tasks.append({"slug": task_slug, "runs": runs})

    return {"current": {"task": current_task, "run": current_run}, "tasks": tasks}


async def get_runs(request: Request) -> JSONResponse:
    """GET /api/runs — list all tasks and runs."""
    results_dir = _results_dir(request)
    coral_dir = _coral_dir(request)
    data = _enumerate_runs(results_dir, coral_dir)
    return JSONResponse(data)


async def switch_run(request: Request) -> JSONResponse:
    """POST /api/runs/switch — switch to a different run."""
    import asyncio

    from coral.web.events import FileWatcher

    body = await request.json()
    task = body.get("task")
    run = body.get("run")
    if not task or not run:
        return JSONResponse({"error": "task and run required"}, status_code=400)

    results_dir = _results_dir(request)
    new_coral_dir = results_dir / task / run / ".coral"
    if not new_coral_dir.is_dir():
        return JSONResponse({"error": "run not found"}, status_code=404)

    app = request.app

    async with app.state._switch_lock:
        # Stop old watcher
        old_watcher = app.state.watcher
        old_watcher.stop()
        app.state._watcher_task.cancel()
        try:
            await app.state._watcher_task
        except asyncio.CancelledError:
            pass

        # Switch coral_dir
        app.state.coral_dir = new_coral_dir.resolve()

        # Start new watcher, reusing subscriber list
        new_watcher = FileWatcher(
            app.state.coral_dir,
            subscribers=old_watcher._subscribers,
        )
        app.state.watcher = new_watcher
        app.state._watcher_task = asyncio.create_task(new_watcher.run())

        # Broadcast switch event
        new_watcher._broadcast({
            "event": "run:switched",
            "data": {"task": task, "run": run},
        })

    return JSONResponse({"ok": True, "task": task, "run": run})


async def get_status(request: Request) -> JSONResponse:
    """GET /api/status — return overall run status."""
    from coral.hub.attempts import read_attempts
    from coral.web.logs import list_log_files

    coral_dir = _coral_dir(request)

    # Manager liveness
    pid_file = coral_dir / "public" / "manager.pid"
    manager_alive = False
    manager_pid = None
    if pid_file.exists():
        try:
            manager_pid = int(pid_file.read_text().strip())
            os.kill(manager_pid, 0)
            manager_alive = True
        except (ProcessLookupError, PermissionError, ValueError):
            pass
    is_docker = not manager_alive and is_docker_run_alive(coral_dir)
    if is_docker:
        manager_alive = True

    # Eval count
    eval_count_file = coral_dir / "public" / "eval_count"
    eval_count = 0
    if eval_count_file.exists():
        try:
            eval_count = int(eval_count_file.read_text().strip())
        except ValueError:
            pass

    # Attempts summary
    attempts = read_attempts(str(coral_dir))
    scored = [a for a in attempts if a.score is not None]
    minimize = _direction(request) == "minimize"
    best_fn = min if minimize else max
    best = best_fn(scored, key=lambda a: a.score or 0.0) if scored else None

    # Per-agent status
    agent_logs = list_log_files(coral_dir)
    agents_status: list[dict[str, Any]] = []

    # Read per-agent PID map for process liveness checks.
    # Skip for Docker runs — container-internal PIDs aren't valid on the host.
    agent_pid_map: dict[str, int] = {}
    pid_map_file = coral_dir / "public" / "agent_pids.json"
    if not is_docker and pid_map_file.exists():
        try:
            agent_pid_map = json.loads(pid_map_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: read agent.pids (plain PID list) and check if any are alive
    any_agent_alive = False
    if not agent_pid_map:
        pids_file = coral_dir / "public" / "agent.pids"
        if pids_file.exists():
            try:
                for line in pids_file.read_text().strip().splitlines():
                    pid = int(line.strip())
                    try:
                        os.kill(pid, 0)
                        any_agent_alive = True
                        break
                    except (ProcessLookupError, PermissionError):
                        pass
            except (ValueError, OSError):
                pass

    # If agent processes are alive but manager.pid is missing, treat as alive
    if not manager_alive and (agent_pid_map or any_agent_alive):
        manager_alive = True

    import time

    for agent_id, logs in agent_logs.items():
        latest = max(logs, key=lambda l: l["modified"])
        age = time.time() - latest["modified"]

        agent_pid = agent_pid_map.get(agent_id)
        if agent_pid:
            # Direct PID check — most reliable
            try:
                os.kill(agent_pid, 0)
                status = "active"
            except (ProcessLookupError, PermissionError):
                status = "stopped"
        elif any_agent_alive or is_docker:
            # Container or agent.pids says something is running but no per-agent mapping
            status = "active" if age < 300 else "idle"
        else:
            # No PID info — log recency as last resort
            status = "active" if age < 120 else "stopped"

        agent_attempts = [a for a in attempts if a.agent_id == agent_id]
        agent_scored = [a for a in agent_attempts if a.score is not None]
        agent_best = best_fn(agent_scored, key=lambda a: a.score or 0.0) if agent_scored else None

        agents_status.append({
            "agent_id": agent_id,
            "status": status,
            "sessions": len(logs),
            "last_activity": latest["modified"],
            "attempts": len(agent_attempts),
            "best_score": agent_best.score if agent_best else None,
        })

    return JSONResponse({
        "manager_alive": manager_alive,
        "manager_pid": manager_pid,
        "eval_count": eval_count,
        "total_attempts": len(attempts),
        "scored_attempts": len(scored),
        "crashed_attempts": len([a for a in attempts if a.status == "crashed"]),
        "best_score": best.score if best else None,
        "best_title": best.title if best else None,
        "agents": agents_status,
    })
