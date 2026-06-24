"""Agent subprocess lifecycle — protocol, handle, and shared helpers."""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class AgentRuntime(Protocol):
    """Protocol that all agent runtimes must implement."""

    def start(
        self,
        worktree_path: Path,
        coral_md_path: Path,
        model: str = "sonnet",
        runtime_options: dict[str, Any] | None = None,
        max_turns: int = 0,
        log_dir: Path | None = None,
        verbose: bool = False,
        resume_session_id: str | None = None,
        prompt: str | None = None,
        prompt_source: str | None = None,
        task_name: str | None = None,
        task_description: str | None = None,
        gateway_url: str | None = None,
        gateway_api_key: str | None = None,
        run_as_user: dict[str, Any] | None = None,
    ) -> AgentHandle: ...

    def extract_session_id(self, log_path: Path) -> str | None: ...

    @property
    def instruction_filename(self) -> str:
        """Filename for the agent's instruction file (e.g. CLAUDE.md, AGENTS.md)."""
        ...

    @property
    def shared_dir_name(self) -> str:
        """Directory name for shared state (notes, skills, etc.) in each worktree.

        Each runtime uses its native directory so agents get built-in
        config/skill discovery: `.claude`, `.codex`, `.opencode`, etc.
        """
        ...


def apply_run_as_user(env: dict[str, str], run_as_user: dict[str, Any] | None) -> dict[str, Any]:
    """Translate a ``run_as_user`` spec into Popen kwargs, adjusting ``env``.

    ``run_as_user`` is ``{"uid", "gid", "home"}`` from the manager's
    OS-user-isolation path (or None). When set, the child is launched as that
    uid/gid (Popen drops privileges before exec — requires a root parent) and
    its HOME/USER are pointed at the agent's home so the runtime CLI finds its
    credentials there. Returns kwargs to splat into ``subprocess.Popen(...)``;
    empty dict when isolation is off.
    """
    if not run_as_user:
        return {}
    home = run_as_user.get("home")
    if home:
        env["HOME"] = home
        env["USER"] = env["LOGNAME"] = run_as_user.get("name", "agent")
    return {"user": run_as_user["uid"], "group": run_as_user["gid"]}


@dataclass
class AgentHandle:
    """Handle to a running agent subprocess."""

    agent_id: str
    process: subprocess.Popen | None
    worktree_path: Path
    log_path: Path
    session_id: str | None = None
    _log_file: object | None = None  # keep reference to prevent GC closing the file
    # Optional per-agent stderr capture under
    # coral_dir/public/diagnostics/<agent_id>/agent.err. When present,
    # AgentHandle.stop() closes the handle so we do not leak FDs across
    # restart churn. None when the runtime did not split stderr.
    err_file: object | None = None
    err_path: Path | None = None

    @property
    def alive(self) -> bool:
        if self.process is None:
            return False
        return self.process.poll() is None

    def _close_pipes(self) -> None:
        """Close stdout/stderr pipes to prevent FD leaks."""
        if self.process:
            for pipe in (self.process.stdout, self.process.stderr):
                if pipe:
                    try:
                        pipe.close()
                    except Exception:
                        pass

    def stop(self) -> None:
        if self.process and self.alive:
            pid = self.process.pid
            logger.info(f"Stopping agent {self.agent_id} (PID {pid})")
            # Kill the entire process group (agent runs in its own session
            # via start_new_session=True) to prevent zombie child processes
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning(f"Agent {self.agent_id} didn't stop, killing process group...")
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    self.process.kill()
                self.process.wait(timeout=5)
        self._close_pipes()
        if self._log_file:
            try:
                self._log_file.close()
            except Exception:
                pass
        if self.err_file is not None:
            try:
                self.err_file.close()  # type: ignore[attr-defined]
            except Exception:
                pass

    def interrupt(self) -> None:
        """Interrupt a running agent via SIGINT (like Ctrl+C).

        Claude Code handles SIGINT gracefully — it saves the session so it can
        be resumed later. Callers extract the session_id themselves via the
        runtime (each CLI emits a different log format).
        """
        if not self.process or not self.alive:
            return

        pid = self.process.pid
        logger.info(f"Interrupting agent {self.agent_id} (PID {pid}) with SIGINT")

        # Send SIGINT to process group (same as Ctrl+C)
        try:
            os.killpg(os.getpgid(pid), signal.SIGINT)
        except (ProcessLookupError, PermissionError):
            self.process.send_signal(signal.SIGINT)

        # Wait for graceful exit
        try:
            self.process.wait(timeout=15)
            logger.info(f"Agent {self.agent_id} exited after SIGINT (rc={self.process.returncode})")
        except subprocess.TimeoutExpired:
            logger.warning(f"Agent {self.agent_id} didn't stop after SIGINT, sending SIGTERM...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

        self._close_pipes()
        if self._log_file:
            try:
                self._log_file.close()
            except Exception:
                pass
        if self.err_file is not None:
            try:
                self.err_file.close()  # type: ignore[attr-defined]
            except Exception:
                pass

    def __del__(self) -> None:
        """Safety net: ensure process and file handles are cleaned up on GC."""
        try:
            if self.process and self.process.poll() is None:
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    self.process.kill()
                self.process.wait(timeout=5)
            self._close_pipes()
            if self._log_file:
                self._log_file.close()
            if self.err_file is not None:
                self.err_file.close()  # type: ignore[attr-defined]
        except Exception:
            pass


def write_coral_log_entry(
    log_file: IO[str],
    prompt: str,
    source: str,
    agent_id: str,
    session_id: str | None = None,
    task_name: str | None = None,
    task_description: str | None = None,
) -> None:
    """Write a CORAL prompt entry to the agent's stream-json log.

    These entries use type="coral" so the web UI can identify and highlight them.
    Source values: "start", "heartbeat:reflect", "heartbeat:consolidate", "restart".
    """
    entry: dict[str, Any] = {
        "type": "coral",
        "subtype": "prompt",
        "source": source,
        "agent_id": agent_id,
        "prompt": prompt,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if session_id:
        entry["session_id"] = session_id
    if task_name:
        entry["task_name"] = task_name
    if task_description:
        entry["task_description"] = task_description
    log_file.write(json.dumps(entry) + "\n")
    log_file.flush()
