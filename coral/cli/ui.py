"""Commands: ui."""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
from pathlib import Path

from coral.cli._helpers import find_coral_dir

DEFAULT_UI_PORT = 8420
UI_PORT_SEARCH_LIMIT = 20


def _ensure_ui_built() -> None:
    """Auto-build the React frontend if static files are missing or stale."""
    static_dir = Path(__file__).parent.parent / "web" / "static"
    index_html = static_dir / "index.html"

    repo_root = Path(__file__).parent.parent.parent
    web_dir = repo_root / "web"

    if not (web_dir / "package.json").exists():
        if index_html.exists():
            return
        print(
            "Error: Dashboard not built and web/ source not found.\n"
            "Run from the repo root:  cd web && npm install && npm run build",
            file=sys.stderr,
        )
        sys.exit(1)

    needs_build = not index_html.exists()
    if not needs_build:
        build_time = index_html.stat().st_mtime
        src_dir = web_dir / "src"
        if src_dir.is_dir():
            for src_file in src_dir.rglob("*"):
                if src_file.is_file() and src_file.stat().st_mtime > build_time:
                    needs_build = True
                    break
        for cfg in ("package.json", "vite.config.ts", "tsconfig.json", "index.html"):
            cfg_path = web_dir / cfg
            if cfg_path.exists() and cfg_path.stat().st_mtime > build_time:
                needs_build = True
                break

    if not needs_build:
        return

    print("[coral] Building dashboard frontend...")

    needs_install = not (web_dir / "node_modules").exists()
    if not needs_install:
        pkg_mtime = (web_dir / "package.json").stat().st_mtime
        lock_file = web_dir / "node_modules" / ".package-lock.json"
        if lock_file.exists():
            needs_install = pkg_mtime > lock_file.stat().st_mtime
        else:
            needs_install = True

    if needs_install:
        print("[coral]   npm install...")
        result = subprocess.run(
            ["npm", "install"],
            cwd=web_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            output = (result.stdout + "\n" + result.stderr).strip()
            print(f"Error: npm install failed:\n{output}", file=sys.stderr)
            sys.exit(1)

    print("[coral]   npm run build...")
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=web_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        output = (result.stdout + "\n" + result.stderr).strip()
        print(f"Error: npm build failed:\n{output}", file=sys.stderr)
        sys.exit(1)

    print("[coral]   Done.")


def _ensure_ui_deps() -> None:
    """Auto-install UI dependencies if missing."""
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        print("[coral] UI dependencies not installed. Running: uv sync --extra ui ...")
        result = subprocess.run(
            ["uv", "sync", "--extra", "ui"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            output = (result.stdout + "\n" + result.stderr).strip()
            print(f"Error: failed to install UI dependencies:\n{output}", file=sys.stderr)
            sys.exit(1)
        print("[coral] UI dependencies installed.")


def _wire_chat_callbacks(app, port: int) -> None:
    """Give the chat module a localhost URL + token for the approval hook.

    The PreToolUse hook (coral/hooks/pretooluse_gate.py) calls back to the
    running dashboard to gate `coral start`. It always targets 127.0.0.1
    regardless of the dashboard's bind host, and authenticates with a
    per-process token.
    """
    import secrets

    app.state.chat_callback_base_url = f"http://127.0.0.1:{port}"
    app.state.chat_callback_token = secrets.token_urlsafe(32)
    app.state.chat_gate_mode = "bypass"


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _find_available_port(host: str, preferred: int = DEFAULT_UI_PORT) -> int:
    for port in range(preferred, preferred + UI_PORT_SEARCH_LIMIT):
        if _port_available(host, port):
            return port
    raise RuntimeError(
        f"No available dashboard port found on {host} in "
        f"{preferred}-{preferred + UI_PORT_SEARCH_LIMIT - 1}."
    )


def _resolve_ui_port(host: str, requested_port: int | None) -> int:
    if requested_port is not None:
        if _port_available(host, requested_port):
            return requested_port
        raise RuntimeError(
            f"Dashboard port {requested_port} is already in use on {host}. "
            f"Run `coral ui --port {requested_port + 1}` or stop the process using that port."
        )

    port = _find_available_port(host, DEFAULT_UI_PORT)
    if port != DEFAULT_UI_PORT:
        print(f"[coral] Dashboard port {DEFAULT_UI_PORT} is in use; using {port}.")
    return port


def start_ui_background(
    coral_dir: Path,
    port: int = DEFAULT_UI_PORT,
    host: str = "127.0.0.1",
) -> None:
    """Start the web dashboard in a background thread."""
    _ensure_ui_deps()
    try:
        import uvicorn
    except ImportError:
        print(
            "Error: Web UI dependencies still not available after install.",
            file=sys.stderr,
        )
        return

    _ensure_ui_built()

    import threading

    from coral.web import create_app

    results_dir = coral_dir.resolve().parent.parent.parent
    app = create_app(coral_dir, results_dir=results_dir)
    if not _port_available(host, port):
        fallback_port = _find_available_port(host, port + 1)
        print(f"[coral] Dashboard port {port} is in use; using {fallback_port}.")
        port = fallback_port
    url = f"http://{host}:{port}"
    _wire_chat_callbacks(app, port)

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    print(f"Dashboard:     {url}")

    import webbrowser

    webbrowser.open(url)


def _latest_run_coral_dir(results_root: Path) -> Path | None:
    """Newest ``<task>/<run>/.coral`` under the runs root, or None."""
    if not results_root.is_dir():
        return None
    candidates: list[Path] = []
    for task_dir in results_root.iterdir():
        if not task_dir.is_dir():
            continue
        for run_dir in task_dir.iterdir():
            cd = run_dir / ".coral"
            if cd.is_dir():
                candidates.append(cd)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _server_placeholder() -> Path:
    """A stable empty ``.coral`` used as the initial view when no run exists.

    The read endpoints (attempts/notes/logs/...) read this dir and return
    empty — no per-endpoint null-handling needed. The UI re-points to a real
    run via ``/api/runs/switch`` once one is selected.
    """
    import os

    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    placeholder = base / "coral" / "server-placeholder" / ".coral"
    (placeholder / "public").mkdir(parents=True, exist_ok=True)
    return placeholder


def cmd_server(args: argparse.Namespace) -> None:
    """Launch the host-level server (dashboard + chat, no run required).

    Examples:
      coral server
      coral server --results ./results --port 8500
    """
    _ensure_ui_deps()
    import uvicorn

    _ensure_ui_built()

    results_root = (
        Path(args.results).expanduser().resolve() if args.results else Path.cwd() / "results"
    )
    results_root.mkdir(parents=True, exist_ok=True)
    coral_dir = _latest_run_coral_dir(results_root) or _server_placeholder()

    try:
        port = _resolve_ui_port(args.host, args.port)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    from coral.web import create_app

    app = create_app(coral_dir, results_dir=results_root)
    _wire_chat_callbacks(app, port)
    url = f"http://{args.host}:{port}"
    print(f"CORAL Server: {url}")
    print(f"Runs root:    {results_root}")
    print("Dashboard + chat ready (no run required). Stop with Ctrl-C.\n")

    if not args.no_open:
        import webbrowser

        webbrowser.open(url)

    uvicorn.run(app, host=args.host, port=port, log_level="warning")


def cmd_ui(args: argparse.Namespace) -> None:
    """Launch the web dashboard.

    Examples:
      coral ui                      Open dashboard in browser
      coral ui --port 9000          Use custom port
    """
    _ensure_ui_deps()
    import uvicorn

    _ensure_ui_built()

    coral_dir = find_coral_dir(getattr(args, "task", None), getattr(args, "run", None))
    try:
        port = _resolve_ui_port(args.host, args.port)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    from coral.web import create_app

    results_dir = coral_dir.resolve().parent.parent.parent
    app = create_app(coral_dir, results_dir=results_dir)
    _wire_chat_callbacks(app, port)
    url = f"http://{args.host}:{port}"
    print(f"CORAL Dashboard: {url}")
    print(f"Serving data from: {coral_dir}")

    # Write PID so `coral stop` can kill us
    pid_file = coral_dir / "public" / "ui.pid"
    import os

    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))

    if not args.no_open:
        import webbrowser

        webbrowser.open(url)

    print("Stop with: coral stop\n")

    try:
        uvicorn.run(app, host=args.host, port=port, log_level="warning")
    finally:
        pid_file.unlink(missing_ok=True)
