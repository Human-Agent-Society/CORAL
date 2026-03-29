"""Agent subprocess lifecycle — protocol, handle, and shared helpers."""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
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
        max_turns: int = 200,
        log_dir: Path | None = None,
        verbose: bool = False,
        resume_session_id: str | None = None,
        prompt: str | None = None,
        prompt_source: str | None = None,
        task_name: str | None = None,
        task_description: str | None = None,
        gateway_url: str | None = None,
        gateway_api_key: str | None = None,
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


@dataclass
class AgentHandle:
    """Handle to a running agent subprocess."""

    agent_id: str
    process: subprocess.Popen | None
    worktree_path: Path
    log_path: Path
    session_id: str | None = None
    _log_file: object | None = None  # keep reference to prevent GC closing the file

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

    def interrupt(self) -> str | None:
        """Interrupt a running agent via SIGINT (like Ctrl+C).

        Claude Code handles SIGINT gracefully — it saves the session so it can
        be resumed later. Returns the session_id extracted from the log, or None.
        """
        if not self.process or not self.alive:
            return _extract_session_id(self.log_path)

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

        return _extract_session_id(self.log_path)

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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if session_id:
        entry["session_id"] = session_id
    if task_name:
        entry["task_name"] = task_name
    if task_description:
        entry["task_description"] = task_description
    log_file.write(json.dumps(entry) + "\n")
    log_file.flush()


def _extract_session_id(log_path: Path) -> str | None:
    """Extract session_id from a stream-json log.

    Checks (in order): result lines, then any line with a session_id
    (system init, assistant messages, etc.) — scanning from the end.
    """
    try:
        lines = log_path.read_text().strip().splitlines()
        # First pass: look for a "result" line (most authoritative)
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "result" and data.get("session_id"):
                    return data["session_id"]
            except json.JSONDecodeError:
                continue
        # Second pass: fall back to any line with session_id
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                sid = data.get("session_id")
                if sid:
                    return sid
            except json.JSONDecodeError:
                continue
    except Exception as e:
        logger.debug(f"Failed to extract session_id from {log_path}: {e}")
    return None
