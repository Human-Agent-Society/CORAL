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
    has_tmux,
    in_tmux,
    kill_orphaned_agents,
    kill_tmux_session,
    read_direction,
    save_tmux_session_name,
    setup_logging,
)


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
    """Reconstruct the coral start command with --no-tmux added."""
    cmd = [_resolved_python(), "-m", "coral.cli", "start"]
    cmd.extend(["--config", str(Path(args.config).resolve())])
    if args.agents:
        cmd.extend(["--agents", str(args.agents)])
    if args.model:
        cmd.extend(["--model", args.model])
    if args.runtime:
        cmd.extend(["--runtime", args.runtime])
    if args.research is True:
        cmd.append("--research")
    elif args.research is False:
        cmd.append("--no-research")
    if args.verbose:
        cmd.append("--verbose")
    if args.ui:
        cmd.append("--ui")
    cmd.append("--no-tmux")
    return cmd


def _start_in_tmux(args: argparse.Namespace) -> None:
    """Create a tmux session and run coral start inside it."""
    from coral.config import CoralConfig

    config_path = Path(args.config).resolve()
    config = CoralConfig.from_yaml(config_path)
    task_name = config.task.name.replace(" ", "-").lower()
    session_name = f"coral-{task_name}"

    # Kill existing session with same name if it exists
    subprocess.run(
        ["tmux", "kill-session", "-t", session_name],
        capture_output=True,
    )

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

    # Pre-create the results directory so we can save tmux markers there
    from coral.workspace.setup import _slugify
    results_dir = (config.task_dir or config_path.parent or Path.cwd()) / config.workspace.results_dir
    task_dir = results_dir / _slugify(config.task.name)
    task_dir.mkdir(parents=True, exist_ok=True)
    save_tmux_session_name(task_dir, session_name)

    print(f"Started CORAL in tmux session: {session_name}")
    print(f"  Attach:  tmux attach -t {session_name}")
    print("  Status:  coral status")
    print("  Stop:    coral stop")


def _resume_in_tmux(args: argparse.Namespace, coral_dir: Path) -> None:
    """Resume CORAL inside a tmux session."""
    from coral.config import CoralConfig

    config_path = coral_dir / "config.yaml"
    config = CoralConfig.from_yaml(config_path)
    task_name = config.task.name.replace(" ", "-").lower()
    session_name = f"coral-{task_name}"

    subprocess.run(
        ["tmux", "kill-session", "-t", session_name],
        capture_output=True,
    )

    cmd = [_resolved_python(), "-m", "coral.cli", "resume"]
    if args.task:
        cmd.extend(["--task", args.task])
    if args.run:
        cmd.extend(["--run", args.run])
    if args.model:
        cmd.extend(["--model", args.model])
    if getattr(args, "verbose", False):
        cmd.append("--verbose")
    if getattr(args, "ui", False):
        cmd.append("--ui")
    cmd.append("--no-tmux")
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
    if not args.no_tmux and not in_tmux() and has_tmux():
        _start_in_tmux(args)
        return

    if not args.no_tmux and not in_tmux() and not has_tmux():
        print(
            "Warning: tmux is not installed. Running in foreground mode.\n"
            "  Install tmux for background session support: brew install tmux (macOS) / apt install tmux (Linux)\n",
            file=sys.stderr,
        )

    from coral.agent.manager import AgentManager
    from coral.config import CoralConfig
    from coral.cli.validation import validate_task

    verbose = args.verbose
    setup_logging(verbose=verbose)

    config_path = Path(args.config).resolve()
    config = CoralConfig.from_yaml(config_path)

    task_dir = config_path.parent
    config.task_dir = task_dir
    errors = validate_task(task_dir)
    if errors:
        print("Task validation errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    if args.agents:
        config.agents.count = args.agents
    if args.runtime:
        config.agents.runtime = args.runtime
    if args.model:
        config.agents.model = args.model
    elif args.runtime:
        # No explicit --model but runtime changed: use runtime-specific default
        from coral.agent.registry import default_model_for_runtime
        default_model = default_model_for_runtime(args.runtime)
        if default_model:
            config.agents.model = default_model
    if args.research is not None:
        config.agents.research = args.research

    if verbose:
        print(f"[coral] Config:     {args.config}")
        print(f"[coral] Task:       {config.task.name}")
        print(f"[coral] Grader:     {config.grader.type or 'auto (eval/grader.py)'}")
        print(f"[coral] Agents:     {config.agents.count}")
        print(f"[coral] Model:      {config.agents.model}")
        print(f"[coral] Max turns:  {config.agents.max_turns}")
        print(f"[coral] Results:    {config.workspace.results_dir}")
        print(f"[coral] Repo path:  {config.workspace.repo_path}")
        if config.task.seed:
            print(f"[coral] Seed files: {config.task.seed}")
        print()

    manager = AgentManager(config, verbose=verbose, config_dir=config_path.parent)
    handles = manager.start_all()

    print(f"Started {len(handles)} agent(s):")
    for h in handles:
        print(f"  {h.agent_id}: PID {h.process.pid if h.process else '?'} @ {h.worktree_path}")

    assert manager.paths is not None
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

    if args.ui:
        from coral.cli.ui import start_ui_background

        start_ui_background(manager.paths.coral_dir)

    if config.agents.count == 1 and verbose:
        print("\nAgent running...\n")
        manager.wait_for_completion()
    else:
        print("\nMonitoring agents...")
        manager.monitor_loop()


def cmd_resume(args: argparse.Namespace) -> None:
    """Resume a previous CORAL run."""
    from coral.agent.manager import AgentManager
    from coral.config import CoralConfig

    verbose = getattr(args, "verbose", False)
    setup_logging(verbose=verbose)

    coral_dir = find_coral_dir(
        getattr(args, "task", None),
        getattr(args, "run", None),
    )

    if not getattr(args, "no_tmux", False):
        existing_session = find_tmux_session(coral_dir)
        if existing_session:
            print(f"Found existing tmux session: {existing_session}")
            print("Attaching...")
            os.execvp("tmux", ["tmux", "attach", "-t", existing_session])
            return

    if not getattr(args, "no_tmux", False) and not in_tmux() and has_tmux():
        _resume_in_tmux(args, coral_dir)
        return

    if not getattr(args, "no_tmux", False) and not in_tmux() and not has_tmux():
        print(
            "Warning: tmux is not installed. Running in foreground mode.\n"
            "  Install tmux for background session support: brew install tmux (macOS) / apt install tmux (Linux)\n",
            file=sys.stderr,
        )

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
        except ProcessLookupError:
            pass

    config_path = coral_dir / "config.yaml"
    if not config_path.exists():
        print(f"Error: No config.yaml found in {coral_dir}", file=sys.stderr)
        sys.exit(1)

    config = CoralConfig.from_yaml(config_path)

    if args.model:
        config.agents.model = args.model

    from coral.workspace.setup import reconstruct_paths

    paths = reconstruct_paths(coral_dir)

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

    manager = AgentManager(config, verbose=verbose)
    handles = manager.resume_all(paths)

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
            save_tmux_session_name(
                paths.coral_dir / "public", session_name, owned=coral_owns
            )

    if getattr(args, "ui", False):
        from coral.cli.ui import start_ui_background

        start_ui_background(paths.coral_dir)

    print("\nMonitoring agents...")
    manager.monitor_loop()


def _stop_ui(coral_dir: Path) -> None:
    """Stop a standalone UI process if running."""
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


def _stop_one(coral_dir: Path) -> None:
    """Stop a single CORAL run by its .coral directory."""
    pid_file = coral_dir / "public" / "manager.pid"
    agent_pids_file = coral_dir / "public" / "agent.pids"

    _stop_ui(coral_dir)

    if not pid_file.exists():
        print("No running CORAL manager found.")
        kill_orphaned_agents(agent_pids_file)
        kill_tmux_session(coral_dir)
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
            except ProcessLookupError:
                print("Manager stopped.")
                kill_tmux_session(coral_dir)
                return
        print("Manager didn't stop gracefully. Force killing...")
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        kill_orphaned_agents(agent_pids_file)
        pid_file.unlink(missing_ok=True)
        kill_tmux_session(coral_dir)
    except ProcessLookupError:
        print(f"Manager (PID {pid}) not running. Cleaning up.")
        kill_orphaned_agents(agent_pids_file)
        pid_file.unlink(missing_ok=True)
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
        coral_dir = find_coral_dir(getattr(args, "task", None), getattr(args, "run", None))
        _stop_one(coral_dir)


def cmd_status(args: argparse.Namespace) -> None:
    """Show agent status and leaderboard."""
    from coral.hub.attempts import (
        format_leaderboard,
        format_status_summary,
        get_leaderboard,
    )

    coral_dir = find_coral_dir(getattr(args, "task", None), getattr(args, "run", None))

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
        except ProcessLookupError:
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
