"""Commands: start, resume, stop, status."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from coral.cli._helpers import (
    find_coral_dir,
    find_tmux_session,
    has_docker,
    has_docker_marker,
    has_tmux,
    in_docker,
    in_tmux,
    is_docker_run_alive,
    kill_docker_container,
    kill_orphaned_agents,
    kill_tmux_session,
    kill_ui,
    pick_run,
    read_direction,
    save_docker_container_name,
    save_tmux_session_name,
    setup_logging,
)
from coral.config import CoralConfig
from coral.workspace.project import slugify


def _resolved_python() -> str:
    """Return the absolute path to the Python interpreter with coral installed.

    Checks for a local venv first (preserving the venv symlink so that
    venv site-packages are used), then falls back to sys.executable.
    Using Path.resolve() would follow the venv symlink to the system
    Python which doesn't have coral installed.
    """
    # If we're already running inside a venv, use it directly
    if sys.prefix != sys.base_prefix:
        return os.path.abspath(sys.executable)

    # Look for a local .venv relative to the coral package
    coral_pkg = Path(__file__).resolve().parent.parent.parent
    for venv_name in (".venv", "venv"):
        venv_python = coral_pkg / venv_name / "bin" / "python"
        if venv_python.exists():
            return str(venv_python)

    # Fallback: current interpreter (absolute, but don't resolve symlinks)
    return os.path.abspath(sys.executable)


def _tmux_env() -> dict[str, str]:
    """Build an environment for tmux that allows nested session creation."""
    env = dict(os.environ)
    env.pop("TMUX", None)  # Allow creating sessions even if nested
    return env


def _build_coral_command(args: argparse.Namespace) -> list[str]:
    """Reconstruct the coral start command with run.session=local added."""
    cmd = [_resolved_python(), "-m", "coral.cli", "start"]
    cmd.extend(["--config", str(Path(args.config).resolve())])
    # Forward user overrides, then force local (inner process is already in tmux)
    cmd.extend(getattr(args, "overrides", []))
    cmd.append("run.session=local")
    return cmd


def _start_in_tmux(args: argparse.Namespace, config: CoralConfig) -> None:
    """Create a tmux session and run coral start inside it."""
    task_name = slugify(config.task.name)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    session_name = f"coral-{task_name}-{timestamp}"

    coral_cmd = _build_coral_command(args)
    shell_cmd = " ".join(f"'{c}'" if " " in c else c for c in coral_cmd)

    result = subprocess.run(
        ["tmux", "new-session", "-d", "-s", session_name, shell_cmd],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
        env=_tmux_env(),
    )
    if result.returncode != 0:
        print(f"Error creating tmux session: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    # Pre-create the results directory so we can save tmux markers there.
    # Must match create_project()'s resolution: relative to CWD, not task config dir.
    results_dir = Path(config.workspace.results_dir).resolve()
    task_dir = results_dir / slugify(config.task.name)
    task_dir.mkdir(parents=True, exist_ok=True)
    save_tmux_session_name(task_dir, session_name)

    print(f"Started CORAL in tmux session: {session_name}")
    print(f"  Attach:  tmux attach -t {session_name}")
    print("  Status:  coral status")
    print("  Stop:    coral stop")


_RUNTIME_DOCKER_DIR: dict[str, str] = {
    "claude_code": "claude",
    "codex": "codex",
    "opencode": "opencode",
}


def _ensure_docker_image(config: CoralConfig) -> str:
    """Return the Docker image name, building it if necessary."""
    if config.run.docker_image:
        return config.run.docker_image

    runtime = config.agents.runtime
    docker_dir = _RUNTIME_DOCKER_DIR.get(runtime)
    if docker_dir is None:
        print(
            f"Error: No Docker support for runtime {runtime!r}. "
            f"Supported: {', '.join(sorted(_RUNTIME_DOCKER_DIR))}",
            file=sys.stderr,
        )
        sys.exit(1)

    image = f"coral-{docker_dir}:local"
    coral_pkg = Path(__file__).resolve().parent.parent.parent
    dockerfile = coral_pkg / "docker" / docker_dir / "Dockerfile"
    if not dockerfile.exists():
        print(
            f"Error: No Dockerfile found at {dockerfile} and no docker_image specified.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"Building Docker image '{image}' ...")
    result = subprocess.run(
        ["sudo", "docker", "build", "-f", str(dockerfile), "-t", image, "."],
        cwd=str(coral_pkg),
    )
    if result.returncode != 0:
        print("Error: Docker build failed.", file=sys.stderr)
        sys.exit(1)
    return image


def _build_docker_cmd(
    *,
    container_name: str,
    config_dir: Path,
    host_run_dir: Path,
    repo_path: Path,
    config: CoralConfig,
    image: str,
) -> list[str]:
    """Build the `docker run` command with standard mounts and env vars."""
    cmd: list[str] = [
        "sudo", "docker", "run", "-d",
        "--name", container_name,
        "-v", f"{config_dir}:/task:ro",
        "-v", f"{host_run_dir}:/app/run:rw",
        "-v", f"{repo_path}:/repo:rw",
    ]

    # Mount runtime-specific credentials
    runtime = config.agents.runtime
    docker_dir = _RUNTIME_DOCKER_DIR.get(runtime, "claude")

    if docker_dir == "claude":
        # Persistent Claude home inside the run dir so sessions survive restarts
        claude_home = host_run_dir / ".claude_home"
        claude_home.mkdir(exist_ok=True)
        cmd.extend(["-v", f"{claude_home}:/root/.claude:rw"])
        # Mount host credentials as read-only staging
        claude_config = Path.home() / ".claude"
        if claude_config.is_dir():
            cmd.extend(["-v", f"{claude_config}:/claude-config:ro"])
    elif docker_dir == "codex":
        codex_home = host_run_dir / ".codex_home"
        codex_home.mkdir(exist_ok=True)
        cmd.extend(["-v", f"{codex_home}:/root/.codex:rw"])
        codex_config = Path.home() / ".codex"
        if codex_config.is_dir():
            cmd.extend(["-v", f"{codex_config}:/codex-config:ro"])
    elif docker_dir == "opencode":
        opencode_home = host_run_dir / ".opencode_home"
        opencode_home.mkdir(exist_ok=True)
        cmd.extend(["-v", f"{opencode_home}:/root/.opencode:rw"])
        opencode_config = Path.home() / ".opencode"
        if opencode_config.is_dir():
            cmd.extend(["-v", f"{opencode_config}:/opencode-config:ro"])

    # Pass through API key env vars
    for key, val in os.environ.items():
        if key.endswith("_API_KEY") or key.endswith("_API_TOKEN"):
            cmd.extend(["-e", f"{key}={val}"])

    cmd.extend(["-e", "CORAL_IN_DOCKER=1"])

    if config.run.ui:
        cmd.extend(["-p", "8420:8420"])

    cmd.append(image)
    return cmd


def _run_docker_container(docker_cmd: list[str], container_name: str) -> None:
    """Execute docker run and exit on failure."""
    result = subprocess.run(docker_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error starting Docker container: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"Started CORAL in Docker container: {container_name}")
    print(f"  Logs:    docker logs -f {container_name}")
    print("  Status:  coral status")
    print("  Stop:    coral stop")


def _start_in_docker(args: argparse.Namespace, config: CoralConfig) -> None:
    """Build (if needed) and run coral start inside a Docker container."""
    image = _ensure_docker_image(config)

    task_name = slugify(config.task.name)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    container_name = f"coral-{task_name}-{timestamp}"

    config_path = Path(args.config).resolve()
    config_dir = config_path.parent

    results_dir = Path(config.workspace.results_dir)
    if not results_dir.is_absolute():
        results_dir = (Path.cwd() / results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    task_slug = slugify(config.task.name)
    host_task_dir = results_dir / task_slug
    host_task_dir.mkdir(parents=True, exist_ok=True)
    host_run_dir = host_task_dir / timestamp
    host_run_dir.mkdir(parents=True, exist_ok=True)

    repo_path = Path(config.workspace.repo_path).resolve()

    docker_cmd = _build_docker_cmd(
        container_name=container_name,
        config_dir=config_dir,
        host_run_dir=host_run_dir,
        repo_path=repo_path,
        config=config,
        image=image,
    )
    docker_cmd.extend([
        "start", "--config", f"/task/{config_path.name}",
        "workspace.run_dir=/app/run", "workspace.repo_path=/repo", "run.session=local",
    ])
    docker_cmd.extend(getattr(args, "overrides", []))

    _run_docker_container(docker_cmd, container_name)

    save_docker_container_name(host_run_dir, container_name)
    (host_run_dir / ".coral_host_repo_path").write_text(str(repo_path))
    (host_run_dir / ".coral_host_config_dir").write_text(str(config_dir))

    # Create the "latest" symlink on the host
    latest_link = host_task_dir / "latest"
    rel = os.path.relpath(host_run_dir, host_task_dir)
    if latest_link.is_symlink() or latest_link.exists():
        latest_link.unlink()
    latest_link.symlink_to(rel)


def _resume_in_tmux(args: argparse.Namespace, config: CoralConfig, coral_dir: Path) -> None:
    """Resume CORAL inside a tmux session."""
    task_name = slugify(config.task.name)
    run_name = coral_dir.resolve().parent.name
    session_name = f"coral-{task_name}-{run_name}"

    # Kill stale session with same name (same run being re-resumed)
    subprocess.run(
        ["tmux", "kill-session", "-t", session_name],
        capture_output=True,
    )

    cmd = [_resolved_python(), "-m", "coral.cli", "resume"]
    # Derive task/run from coral_dir path to avoid re-prompting inside tmux.
    # Path structure: results/<task>/<run>/.coral
    resolved = coral_dir.resolve()
    run_name = resolved.parent.name
    task_slug = resolved.parent.parent.name
    if args.task:
        cmd.extend(["--task", args.task])
    else:
        cmd.extend(["--task", task_slug])
    if args.run:
        cmd.extend(["--run", args.run])
    else:
        cmd.extend(["--run", run_name])
    # Forward --instruction flag if provided
    instruction = getattr(args, "instruction", None)
    if instruction:
        cmd.extend(["--instruction", instruction])
    # Forward user overrides, then force local (inner process is already in tmux)
    cmd.extend(getattr(args, "overrides", []))
    cmd.append("run.session=local")
    shell_cmd = " ".join(f"'{c}'" if " " in c else c for c in cmd)

    result = subprocess.run(
        ["tmux", "new-session", "-d", "-s", session_name, shell_cmd],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
        env=_tmux_env(),
    )
    if result.returncode != 0:
        print(f"Error creating tmux session: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    public_dir = coral_dir / "public"
    public_dir.mkdir(parents=True, exist_ok=True)
    save_tmux_session_name(public_dir, session_name)

    print(f"Resumed CORAL in tmux session: {session_name}")
    print(f"  Attach:  tmux attach -t {session_name}")
    print("  Status:  coral status")
    print("  Stop:    coral stop")


def cmd_start(args: argparse.Namespace) -> None:
    """Start CORAL agents."""
    config_path = Path(args.config).resolve()
    config = CoralConfig.from_yaml(config_path)
    overrides = getattr(args, "overrides", [])
    if overrides:
        config = CoralConfig.merge_dotlist(config, overrides)

    session = config.run.session

    if session == "docker" and not in_docker():
        if not has_docker():
            print(
                "Error: docker is not installed but run.session=docker.",
                file=sys.stderr,
            )
            sys.exit(1)
        _start_in_docker(args, config)
        return

    if session == "tmux" and not in_tmux() and has_tmux():
        _start_in_tmux(args, config)
        return

    if session == "tmux" and not in_tmux() and not has_tmux():
        print(
            "Warning: tmux is not installed. Running in foreground mode.\n"
            "  Install tmux for background session support: brew install tmux (macOS) / apt install tmux (Linux)\n",
            file=sys.stderr,
        )

    # Inner process: run.session=local was set to avoid recursion.
    # Restore the original session mode so the saved config preserves user intent
    # (otherwise `coral resume` won't re-launch in the same wrapper).
    if in_tmux():
        config.run.session = "tmux"
    elif in_docker():
        config.run.session = "docker"

    from coral.agent.manager import AgentManager
    from coral.cli.validation import validate_task

    verbose = config.run.verbose
    setup_logging(verbose=verbose)

    task_dir = config_path.parent
    config.task_dir = task_dir
    errors = validate_task(task_dir)
    if errors:
        print("Task validation errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    if verbose:
        print(f"[coral] Config:     {args.config}")
        print(f"[coral] Task:       {config.task.name}")
        print(f"[coral] Grader:     {config.grader.type or 'auto (eval/grader.py)'}")
        print(f"[coral] Agents:     {config.agents.count}")
        print(f"[coral] Model:      {config.agents.model}")
        print(f"[coral] Max turns:  {config.agents.max_turns}")
        print(f"[coral] Results:    {config.workspace.results_dir}")
        print(f"[coral] Repo path:  {config.workspace.repo_path}")
        if config.agents.warmstart.enabled:
            print(f"[coral] Warm-start: enabled")
        print()

    manager = AgentManager(config, verbose=verbose, config_dir=config_path.parent)
    handles = manager.start_all()

    print(f"Started {len(handles)} agent(s):")
    for h in handles:
        print(f"  {h.agent_id}: PID {h.process.pid if h.process else '?'} @ {h.worktree_path}")

    assert manager.paths is not None

    # Save the starting command for reproducibility
    start_cmd = f"coral start -c {args.config}"
    if overrides:
        start_cmd += " " + " ".join(overrides)
    (manager.paths.run_dir / "start_cmd.txt").write_text(start_cmd + "\n")

    print(f"\nRun directory: {manager.paths.run_dir}")
    print(f"Logs:          {manager.paths.coral_dir / 'public' / 'logs'}")

    if in_tmux():
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#S"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            session_name = result.stdout.strip()
            # Mark as owned if coral created this tmux session (via _start_in_tmux)
            coral_owns = session_name.startswith("coral-")
            save_tmux_session_name(
                manager.paths.coral_dir / "public", session_name, owned=coral_owns
            )

    if config.run.ui:
        from coral.cli.ui import start_ui_background

        start_ui_background(manager.paths.coral_dir)

    if config.agents.count == 1 and verbose:
        print("\nAgent running...\n")
        manager.wait_for_completion()
    else:
        print("\nMonitoring agents...")
        manager.monitor_loop()


def _resume_in_docker(args: argparse.Namespace, config: CoralConfig, coral_dir: Path) -> None:
    """Resume CORAL inside a Docker container."""
    image = _ensure_docker_image(config)

    task_name = slugify(config.task.name)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    container_name = f"coral-{task_name}-resume-{timestamp}"

    host_run_dir = coral_dir.resolve().parent

    # Read original host paths saved by _start_in_docker
    config_dir_file = host_run_dir / ".coral_host_config_dir"
    repo_path_file = host_run_dir / ".coral_host_repo_path"
    config_dir = (
        Path(config_dir_file.read_text().strip()) if config_dir_file.exists()
        else Path(config.task_dir or Path.cwd()).resolve()
    )
    repo_path = (
        Path(repo_path_file.read_text().strip()) if repo_path_file.exists()
        else Path(config.workspace.repo_path).resolve()
    )

    docker_cmd = _build_docker_cmd(
        container_name=container_name,
        config_dir=config_dir,
        host_run_dir=host_run_dir,
        repo_path=repo_path,
        config=config,
        image=image,
    )
    docker_cmd.extend([
        "resume",
        "workspace.run_dir=/app/run", "workspace.repo_path=/repo", "run.session=local",
    ])
    instruction = getattr(args, "instruction", None)
    if instruction:
        docker_cmd.extend(["--instruction", instruction])
    docker_cmd.extend(getattr(args, "overrides", []))

    _run_docker_container(docker_cmd, container_name)
    save_docker_container_name(host_run_dir, container_name)


def cmd_resume(args: argparse.Namespace) -> None:
    """Resume a previous CORAL run."""
    from coral.agent.manager import AgentManager

    task = getattr(args, "task", None)
    run = getattr(args, "run", None)
    if task or run or in_docker():
        coral_dir = find_coral_dir(task, run)
    else:
        coral_dir = pick_run(status_filter="stopped", allow_cancel=True)
    if coral_dir is None:
        return

    config_path = coral_dir / "config.yaml"
    if not config_path.exists():
        print(f"Error: No config.yaml found in {coral_dir}", file=sys.stderr)
        sys.exit(1)

    config = CoralConfig.from_yaml(config_path)
    overrides = getattr(args, "overrides", [])
    if overrides:
        config = CoralConfig.merge_dotlist(config, overrides)
        # Persist overrides so eval hooks (which re-read config.yaml) see them
        config.to_yaml(config_path)

    if config.run.session == "docker" and not in_docker():
        if not has_docker():
            print(
                "Error: docker is not installed but run.session=docker.",
                file=sys.stderr,
            )
            sys.exit(1)
        _resume_in_docker(args, config, coral_dir)
        return

    if config.run.session == "tmux":
        existing_session = find_tmux_session(coral_dir)
        if existing_session:
            print(f"Found existing tmux session: {existing_session}")
            print("Attaching...")
            os.execvp("tmux", ["tmux", "attach", "-t", existing_session])
            return

    if config.run.session == "tmux" and not in_tmux() and has_tmux():
        _resume_in_tmux(args, config, coral_dir)
        return

    if config.run.session == "tmux" and not in_tmux() and not has_tmux():
        print(
            "Warning: tmux is not installed. Running in foreground mode.\n"
            "  Install tmux for background session support: brew install tmux (macOS) / apt install tmux (Linux)\n",
            file=sys.stderr,
        )

    verbose = config.run.verbose
    setup_logging(verbose=verbose)

    pid_file = coral_dir / "public" / "manager.pid"
    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)
            print(
                f"Error: Manager already running (PID {pid}). Stop it first with 'coral stop'.",
                file=sys.stderr,
            )
            sys.exit(1)
        except PermissionError:
            print(
                f"Error: Manager already running (PID {pid}). Stop it first with 'coral stop'.",
                file=sys.stderr,
            )
            sys.exit(1)
        except ProcessLookupError:
            pass

    from coral.workspace import reconstruct_paths

    paths = reconstruct_paths(coral_dir)

    # Restore task_dir so relative paths (e.g. gateway config) resolve correctly
    config_dir_file = coral_dir / "config_dir"
    if config_dir_file.exists():
        config.task_dir = Path(config_dir_file.read_text().strip())

    latest_link = paths.task_dir / "latest"
    if latest_link.is_symlink():
        latest_link.unlink()
    if not latest_link.exists():
        rel = os.path.relpath(paths.run_dir, paths.task_dir)
        latest_link.symlink_to(rel)

    if verbose:
        print(f"[coral] Resuming run: {paths.run_dir}")
        print(f"[coral] Task:    {config.task.name}")
        print(f"[coral] Model:   {config.agents.model}")

    instruction = getattr(args, "instruction", None)
    manager = AgentManager(config, verbose=verbose)
    handles = manager.resume_all(paths, instruction=instruction)

    print(f"Resumed {len(handles)} agent(s):")
    for h in handles:
        session_str = f" (session {h.session_id[:12]}...)" if h.session_id else " (fresh)"
        print(f"  {h.agent_id}: PID {h.process.pid if h.process else '?'}{session_str}")

    print(f"\nRun directory: {paths.run_dir}")

    if in_tmux():
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#S"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            session_name = result.stdout.strip()
            # Mark as owned if coral created this tmux session (via _resume_in_tmux)
            coral_owns = session_name.startswith("coral-")
            save_tmux_session_name(paths.coral_dir / "public", session_name, owned=coral_owns)

    if config.run.ui:
        from coral.cli.ui import start_ui_background

        start_ui_background(paths.coral_dir)

    print("\nMonitoring agents...")
    manager.monitor_loop()


def _stop_one(coral_dir: Path) -> None:
    """Stop a single CORAL run by its .coral directory."""
    pid_file = coral_dir / "public" / "manager.pid"
    agent_pids_file = coral_dir / "public" / "agent.pids"

    kill_ui(coral_dir)

    # For Docker-managed runs, stop the container directly.
    # The manager/agent PIDs are container-internal and meaningless on the host.
    if has_docker_marker(coral_dir):
        kill_docker_container(coral_dir)
        pid_file.unlink(missing_ok=True)
        agent_pids_file.unlink(missing_ok=True)
        (coral_dir / "public" / "agent_pids.json").unlink(missing_ok=True)
        return

    try:
        if not pid_file.exists():
            print("No running CORAL manager found.")
            kill_orphaned_agents(agent_pids_file)
            return

        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Sent SIGTERM to manager (PID {pid}).")
            import time

            for _ in range(10):
                time.sleep(0.5)
                try:
                    os.kill(pid, 0)
                except (ProcessLookupError, PermissionError):
                    print("Manager stopped.")
                    return
            print("Manager didn't stop gracefully. Force killing...")
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            kill_orphaned_agents(agent_pids_file)
            pid_file.unlink(missing_ok=True)
        except (ProcessLookupError, PermissionError):
            print(f"Manager (PID {pid}) not running. Cleaning up.")
            kill_orphaned_agents(agent_pids_file)
            pid_file.unlink(missing_ok=True)
    finally:
        kill_docker_container(coral_dir)
        kill_tmux_session(coral_dir)


def cmd_stop(args: argparse.Namespace) -> None:
    """Stop CORAL agents."""
    if getattr(args, "all", False):
        from coral.cli.query import _collect_runs, _find_results_dir

        results_dir = _find_results_dir()
        runs = _collect_runs(results_dir)
        active = [r for r in runs if r["status"] == "running"]
        if not active:
            print("No active runs to stop.")
            return
        print(f"Stopping {len(active)} active run(s)...")
        for r in active:
            print(f"\n--- {r['task']} / {r['run']} ---")
            _stop_one(Path(r["path"]) / ".coral")
        print(f"\nStopped {len(active)} run(s).")
    else:
        task = getattr(args, "task", None)
        run = getattr(args, "run", None)
        if task or run:
            coral_dir = find_coral_dir(task, run)
        else:
            coral_dir = pick_run(status_filter="running", allow_cancel=True)
        if coral_dir is None:
            return
        _stop_one(coral_dir)


def cmd_status(args: argparse.Namespace) -> None:
    """Show agent status and leaderboard."""
    from coral.hub.attempts import (
        format_leaderboard,
        format_status_summary,
        get_leaderboard,
    )

    task = getattr(args, "task", None)
    run = getattr(args, "run", None)
    if task or run:
        coral_dir = find_coral_dir(task, run)
    else:
        coral_dir = pick_run()

    real_coral = coral_dir.resolve()
    run_dir = real_coral.parent
    print(f"Run: {run_dir.name}  ({run_dir})")
    print()

    pid_file = coral_dir / "public" / "manager.pid"
    manager_alive = False
    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)
            manager_alive = True
            print(f"Manager: RUNNING (PID {pid})")
        except PermissionError:
            manager_alive = True
            print(f"Manager: RUNNING (PID {pid})")
        except ProcessLookupError:
            pass

    # Check if managed by a Docker container
    if not manager_alive and is_docker_run_alive(coral_dir):
        manager_alive = True
        docker_marker = run_dir / ".coral_docker_container"
        container_name = docker_marker.read_text().strip() if docker_marker.exists() else "unknown"
        print(f"Manager: RUNNING (Docker container {container_name})")

    if not manager_alive:
        if pid_file.exists():
            print("Manager: NOT RUNNING (stale PID file)")
        else:
            print("Manager: not running")

    logs_dir = coral_dir / "public" / "logs"
    if logs_dir.exists():
        log_files = sorted(logs_dir.glob("*.log"))
        if log_files:
            agent_logs: dict[str, list[Path]] = {}
            for lf in log_files:
                parts = lf.stem.rsplit(".", 1)
                agent_name = parts[0] if len(parts) == 2 else lf.stem
                agent_logs.setdefault(agent_name, []).append(lf)

            print(f"\nAgents: {len(agent_logs)}")
            for agent_name, logs in sorted(agent_logs.items()):
                latest_log = max(logs, key=lambda p: p.stat().st_mtime)
                log_size = latest_log.stat().st_size
                mtime = datetime.fromtimestamp(latest_log.stat().st_mtime)
                age = datetime.now() - mtime
                if age.total_seconds() < 30 and manager_alive:
                    status_str = "ACTIVE"
                elif manager_alive:
                    status_str = f"idle ({int(age.total_seconds())}s since last output)"
                else:
                    status_str = "stopped"
                print(
                    f"  {agent_name}: {status_str}  |  "
                    f"sessions: {len(logs)}  |  "
                    f"latest log: {log_size:,} bytes  |  "
                    f"last activity: {mtime.strftime('%H:%M:%S')}"
                )

    direction = read_direction(coral_dir)
    print()
    summary = format_status_summary(str(coral_dir), direction=direction)
    print(summary)

    top = get_leaderboard(str(coral_dir), top_n=10, direction=direction)
    if top:
        print(f"\n## Leaderboard (top {len(top)})")
        print(format_leaderboard(top))
