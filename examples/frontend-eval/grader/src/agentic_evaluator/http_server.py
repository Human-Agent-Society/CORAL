"""Lightweight HTTP server for serving the generator's frontend during evaluation.

Runs on an ephemeral port in a background thread so the evaluator agent
can navigate the live page via Playwright MCP. The grader spins one up
per evaluation and tears it down after.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

logger = logging.getLogger(__name__)


class _QuietHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler that doesn't log every request to stderr."""

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        logger.debug("http: " + format, *args)


def serve_codebase(directory: Path, port: int = 0) -> tuple[int, Callable[[], None]]:
    """Serve `directory` over HTTP on an ephemeral (or given) port.

    Returns (port, stop) where calling stop() shuts the server down.
    """
    handler = partial(_QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    actual_port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Serving {directory} at http://127.0.0.1:{actual_port}/")

    def stop() -> None:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        logger.info(f"Stopped HTTP server on port {actual_port}")

    return actual_port, stop
