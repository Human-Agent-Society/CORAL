"""Shared CLI helpers: logging, tmux, coral_dir discovery."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path


def setup_logging(verbose: bool = False) -> None:
    """Configure logging. Verbose mode logs to stderr at DEBUG level."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )


def has_tmux() -> bool:
    """Check if tmux is available on the system."""
    import shutil

    return shutil.which("tmux") is not None


def in_tmux() -> bool:
    """Check if we're already running inside a tmux session."""
    return bool(os.environ.get("TMUX"))


def save_tmux_session_name(
    save_dir: Path, session_name: str, *, owned: bool = True
) -> None:
    """Save the tmux session name for coral stop to find.

    Args:
        save_dir: Directory to write marker files (typically coral_dir / "public").
        owned: If True, coral created this session and can kill it on stop.
               If False, coral is running inside a pre-existing session.
    """
    tmux_file = save_dir / ".coral_tmux_session"
    tmux_file.write_text(session_name)
    owned_file = save_dir / ".coral_tmux_owned"
    if owned:
        owned_file.write_text("1")
    else:
        owned_file.unlink(missing_ok=True)


def find_tmux_session(coral_dir: Path) -> str | None:
    """Find an existing tmux session for this CORAL run."""
    for search_dir in [coral_dir / "public", coral_dir.parent]:
        tmux_file = search_dir / ".coral_tmux_session"
        if tmux_file.exists():
            session_name = tmux_file.read_text().strip()
            if session_name:
                result = subprocess.run(
                    ["tmux", "has-session", "-t", session_name],
                    capture_output=True,
                )
                if result.returncode == 0:
                    return session_name
    return None


def _is_tmux_owned(search_dir: Path) -> bool:
    """Check if coral created (owns) the tmux session in this directory."""
    owned_file = search_dir / ".coral_tmux_owned"
    return owned_file.exists()


def kill_tmux_session(coral_dir: Path) -> None:
    """Kill the tmux session associated with this run, if coral owns it.

    If coral is running inside a pre-existing tmux session (not one it created),
    only clean up the marker files without killing the session.
    """
    for search_dir in [coral_dir / "public", coral_dir.parent]:
        tmux_file = search_dir / ".coral_tmux_session"
        if tmux_file.exists():
            session_name = tmux_file.read_text().strip()
            owned = _is_tmux_owned(search_dir)
            if session_name and owned:
                result = subprocess.run(
                    ["tmux", "kill-session", "-t", session_name],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    print(f"Killed tmux session: {session_name}")
            elif session_name and not owned:
                print(f"Left tmux session '{session_name}' running (not created by coral).")
            tmux_file.unlink(missing_ok=True)
            (search_dir / ".coral_tmux_owned").unlink(missing_ok=True)
            return

    # Also check in the task config dir
    config_file = coral_dir / "config.yaml"
    if config_file.exists():
        import yaml

        try:
            with open(config_file) as f:
                cfg = yaml.safe_load(f) or {}
            task_dir = cfg.get("_task_dir")
            if task_dir:
                task_path = Path(task_dir)
                tmux_file = task_path / ".coral_tmux_session"
                if tmux_file.exists():
                    session_name = tmux_file.read_text().strip()
                    owned = _is_tmux_owned(task_path)
                    if session_name and owned:
                        subprocess.run(
                            ["tmux", "kill-session", "-t", session_name],
                            capture_output=True,
                            text=True,
                        )
                        print(f"Killed tmux session: {session_name}")
                    elif session_name and not owned:
                        print(
                            f"Left tmux session '{session_name}' running "
                            "(not created by coral)."
                        )
                    tmux_file.unlink(missing_ok=True)
                    (task_path / ".coral_tmux_owned").unlink(missing_ok=True)
        except Exception:
            pass


def kill_orphaned_agents(agent_pids_file: Path) -> None:
    """Kill agent processes that survived the manager."""
    import signal

    if not agent_pids_file.exists():
        return
    killed = 0
    for line in agent_pids_file.read_text().strip().splitlines():
        try:
            pid = int(line.strip())
            os.killpg(os.getpgid(pid), signal.SIGKILL)
            killed += 1
        except (ProcessLookupError, PermissionError, ValueError, OSError):
            pass
    if killed:
        print(f"Killed {killed} orphaned agent process(es).")
    agent_pids_file.unlink(missing_ok=True)


def read_agent_id() -> str:
    """Read agent ID from .coral_agent_id file in cwd."""
    agent_id_file = Path.cwd() / ".coral_agent_id"
    if agent_id_file.exists():
        return agent_id_file.read_text().strip()
    return "unknown"


def read_direction(coral_dir: Path) -> str:
    """Read grader direction from config. Returns 'maximize' or 'minimize'."""
    config_path = coral_dir / "config.yaml"
    if config_path.exists():
        import yaml

        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        return (config.get("grader") or {}).get("direction", "maximize")
    return "maximize"


def find_coral_dir(task: str | None = None, run: str | None = None) -> Path:
    """Find the .coral directory for a task run.

    Search order:
    1. If --task and --run given: results/<task>/<run>/.coral
    2. If --task given: results/<task>/latest (symlink)
    3. Walk up from cwd looking for results/ dir, pick the sole task or latest
    4. Fall back to .coral_dir breadcrumb in cwd
    """
    # Find results dir by walking up
    results_dir = None
    current = Path.cwd()
    while True:
        candidate = current / "results"
        if candidate.is_dir():
            results_dir = candidate
            break
        if current.parent == current:
            break
        current = current.parent

    if results_dir:
        if task and run:
            coral = results_dir / task / run / ".coral"
            if coral.is_dir():
                return coral
            print(f"Error: Run '{run}' not found for task '{task}'.", file=sys.stderr)
            sys.exit(1)

        if task:
            latest = results_dir / task / "latest"
            if latest.exists():
                resolved = latest.resolve() if latest.is_symlink() else latest
                coral = resolved / ".coral" if (resolved / ".coral").is_dir() else resolved
                return coral
            print(f"Error: Task '{task}' not found in {results_dir}.", file=sys.stderr)
            sys.exit(1)

        # No task specified — auto-detect
        task_dirs = [d for d in results_dir.iterdir() if d.is_dir()]
        if len(task_dirs) == 1:
            task_dir = task_dirs[0]
        elif len(task_dirs) > 1:
            task_dir = max(
                task_dirs,
                key=lambda d: (d / "latest").stat().st_mtime if (d / "latest").exists() else 0,
            )
        else:
            task_dir = None

        if task_dir:
            if run:
                coral = task_dir / run / ".coral"
                if coral.is_dir():
                    return coral
                print(f"Error: Run '{run}' not found in {task_dir}.", file=sys.stderr)
                sys.exit(1)
            latest = task_dir / "latest"
            if latest.exists():
                resolved = latest.resolve() if latest.is_symlink() else latest
                coral = resolved / ".coral" if (resolved / ".coral").is_dir() else resolved
                return coral

    # Fallback: read .coral_dir breadcrumb from cwd
    coral_dir_file = Path.cwd() / ".coral_dir"
    if coral_dir_file.exists():
        try:
            coral_dir = Path(coral_dir_file.read_text().strip()).resolve()
            if coral_dir.is_dir():
                return coral_dir
        except (OSError, ValueError):
            pass

    print(
        "Error: No results directory found. Run 'coral start' first, "
        "or use --task to specify the task name.",
        file=sys.stderr,
    )
    sys.exit(1)
