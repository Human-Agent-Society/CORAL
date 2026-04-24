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


def has_docker() -> bool:
    """Check if docker is available on the system."""
    import shutil

    return shutil.which("docker") is not None


def _docker_needs_sudo() -> bool:
    """Return True if docker requires sudo to run.

    Returns False if docker works without sudo. Returns True if docker
    requires sudo and passwordless sudo is available. Exits with an error
    if docker requires sudo but sudo needs a password.
    """
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return False
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    # Docker without sudo failed — try non-interactive sudo
    try:
        result = subprocess.run(
            ["sudo", "-n", "docker", "info"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    print(
        "Error: Docker requires sudo, but sudo requires a password.\n"
        "Either run with passwordless sudo or add your user to the docker group:\n"
        "  sudo usermod -aG docker $USER\n"
        "Then log out and back in for the change to take effect.",
        file=sys.stderr,
    )
    sys.exit(1)


def docker_cmd() -> list[str]:
    """Return the base docker command, prefixed with sudo if needed."""
    if _docker_needs_sudo():
        return ["sudo", "docker"]
    return ["docker"]


def in_docker() -> bool:
    """Check if we're already running inside a Docker container."""
    if os.environ.get("CORAL_IN_DOCKER") == "1":
        return True
    return Path("/.dockerenv").exists()


def is_docker_container_running(container_name: str) -> bool:
    """Check if a Docker container is currently running."""
    result = subprocess.run(
        [*docker_cmd(), "inspect", "-f", "{{.State.Running}}", container_name],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def has_docker_marker(coral_dir: Path) -> bool:
    """Check if this run is managed by a Docker container."""
    for search_dir in [coral_dir / "public", coral_dir.parent]:
        if (search_dir / ".coral_docker_container").exists():
            return True
    return False


def is_docker_run_alive(coral_dir: Path) -> bool:
    """Check if this run is managed by a live Docker container."""
    run_dir = coral_dir.resolve().parent
    marker = run_dir / ".coral_docker_container"
    if marker.exists():
        name = marker.read_text().strip()
        if name:
            return is_docker_container_running(name)
    return False


def save_docker_container_name(save_dir: Path, container_name: str) -> None:
    """Save the Docker container name for coral stop to find."""
    marker = save_dir / ".coral_docker_container"
    marker.write_text(container_name)


def kill_docker_container(coral_dir: Path) -> None:
    """Stop and remove the Docker container associated with this run."""
    for search_dir in [coral_dir / "public", coral_dir.parent]:
        marker = search_dir / ".coral_docker_container"
        if marker.exists():
            container_name = marker.read_text().strip()
            if container_name:
                stopped = subprocess.run(
                    [*docker_cmd(), "stop", container_name],
                    capture_output=True,
                ).returncode == 0
                # Always try rm (container may already be stopped)
                subprocess.run(
                    [*docker_cmd(), "rm", container_name],
                    capture_output=True,
                )
                if stopped:
                    print(f"Stopped Docker container: {container_name}")
            marker.unlink(missing_ok=True)
            return


def kill_ui(coral_dir: Path) -> None:
    """Stop a standalone UI process if running."""
    import signal

    ui_pid_file = coral_dir / "public" / "ui.pid"
    if not ui_pid_file.exists():
        return
    try:
        pid = int(ui_pid_file.read_text().strip())
        os.kill(pid, signal.SIGKILL)
        print(f"Stopped dashboard (PID {pid}).")
    except (ProcessLookupError, ValueError):
        pass
    ui_pid_file.unlink(missing_ok=True)


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
    1. .coral_dir breadcrumb in cwd (always correct for agents in worktrees)
    2. If --task and --run given: results/<task>/<run>/.coral
    3. If --task given: results/<task>/latest (symlink)
    4. Walk up from cwd looking for results/ dir, pick the sole task or latest
    """
    # Priority 1: read .coral_dir breadcrumb from cwd (agents always have this)
    if not task and not run:
        coral_dir_file = Path.cwd() / ".coral_dir"
        if coral_dir_file.exists():
            try:
                coral_dir = Path(coral_dir_file.read_text().strip()).resolve()
                if coral_dir.is_dir():
                    return coral_dir
            except (OSError, ValueError):
                pass

    # Docker shortcut: run dir is mounted at /run, no results/ tree exists
    if in_docker():
        docker_coral = Path("/app/run/.coral")
        if docker_coral.is_dir():
            return docker_coral

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

    print(
        "Error: No results directory found. Run 'coral start' first, "
        "or use --task to specify the task name.",
        file=sys.stderr,
    )
    sys.exit(1)


def pick_run(status_filter: str | None = None, allow_cancel: bool = False) -> Path | None:
    """Interactively pick a run from the results directory.

    Args:
        status_filter: If set, only show runs with this status ("running" or "stopped").
        allow_cancel: If True, show a cancel option and return None if chosen.

    Returns:
        Path to the selected run's .coral directory, or None if cancelled.
    """
    from coral.cli.query import _collect_runs, _find_results_dir, _relative_time

    results_dir = _find_results_dir()
    runs = _collect_runs(results_dir)

    if status_filter:
        runs = [r for r in runs if r["status"] == status_filter]

    # Sort: running first, then most recent first
    running = [r for r in runs if r["status"] == "running"]
    stopped = [r for r in runs if r["status"] != "running"]
    running.sort(key=lambda r: r["run"], reverse=True)
    stopped.sort(key=lambda r: r["run"], reverse=True)
    runs = running + stopped

    if not runs:
        label = status_filter or "available"
        print(f"No {label} runs found.", file=sys.stderr)
        sys.exit(1)

    if len(runs) == 1:
        r = runs[0]
        print(f"Auto-selected: {r['task']} / {r['run']}")
        return Path(r["path"]) / ".coral"

    # Display table
    tw = max(len("TASK"), max(len(r["task"]) for r in runs)) + 2
    rw = max(len("RUN"), max(len(r["run"]) for r in runs)) + 2
    sw = max(len("STATUS"), 10) + 2

    header = f"{'#':>3}  {'TASK':<{tw}}{'RUN':<{rw}}{'STATUS':<{sw}}{'AGENTS':>7}{'EVALS':>7}{'BEST':>9}"
    print(header)
    print("-" * len(header))

    for i, r in enumerate(runs, 1):
        if r["status"] == "running":
            status_str = "running"
        else:
            status_str = f"stopped {_relative_time(r['run'])}"
        best_str = f"{r['best']:.4f}" if r["best"] is not None else "-"
        print(
            f"{i:>3}  {r['task']:<{tw}}{r['run']:<{rw}}{status_str:<{sw}}"
            f"{r['agents']:>7}{r['attempts']:>7}{best_str:>9}"
        )

    print()
    cancel_hint = ", 0 to cancel" if allow_cancel else ""
    while True:
        try:
            choice = input(f"Select run [1-{len(runs)}{cancel_hint}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(1)
        if allow_cancel and choice == "0":
            return None
        try:
            idx = int(choice)
            if 1 <= idx <= len(runs):
                return Path(runs[idx - 1]["path"]) / ".coral"
        except ValueError:
            pass
        print(f"Invalid choice. Enter a number between 1 and {len(runs)}.")
