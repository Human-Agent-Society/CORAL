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

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    print(f"Dashboard:     {url}")

    import webbrowser

    webbrowser.open(url)


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
