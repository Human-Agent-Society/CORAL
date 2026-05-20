# ABOUTME: Runs Pi coding agent as a CORAL agent runtime.
# ABOUTME: Handles subprocess launch, JSON logging, session extraction, and exit classification.
"""Pi coding agent CLI subprocess lifecycle."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from coral.agent.exit_classifier import classify_by_uptime
from coral.agent.process import open_agent_stderr_for_log_dir
from coral.agent.runtime import AgentHandle, write_coral_log_entry
from coral.workspace.repo import _clean_env

logger = logging.getLogger(__name__)

_PI_TOOLS = "read,bash,edit,write,grep,find,ls"


def _extract_pi_session_id(log_path: Path) -> str | None:
    """Extract a Pi session ID from JSON output."""
    try:
        lines = log_path.read_text().strip().splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get("type") == "session":
                session_id = data.get("id")
                if isinstance(session_id, str) and session_id:
                    return session_id
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            session_id = _find_pi_session_id(data)
            if session_id:
                return session_id
    except Exception as e:
        logger.debug(f"Failed to extract Pi session_id from {log_path}: {e}")
    return None


def _find_pi_session_id(data: Any) -> str | None:
    """Find a Pi session identifier in nested JSON output."""
    if isinstance(data, dict):
        for key in ("session_id", "sessionId", "id"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
        for value in data.values():
            session_id = _find_pi_session_id(value)
            if session_id:
                return session_id
    elif isinstance(data, list):
        for item in data:
            session_id = _find_pi_session_id(item)
            if session_id:
                return session_id
    return None


class PiAgentRuntime:
    """Spawn and manage Pi coding agent CLI subprocesses."""

    @property
    def instruction_filename(self) -> str:
        return "AGENTS.md"

    @property
    def shared_dir_name(self) -> str:
        return ".pi"

    def extract_session_id(self, log_path: Path) -> str | None:
        return _extract_pi_session_id(log_path)

    def classify_exit(
        self,
        log_path: Path,
        exit_code: int | None,
        uptime_seconds: float | None,
        min_clean_runtime_seconds: int = 60,
    ) -> str:
        """Classify a Pi subprocess exit using the uptime fallback."""
        return classify_by_uptime(exit_code, uptime_seconds, min_clean_runtime_seconds)

    def start(
        self,
        worktree_path: Path,
        coral_md_path: Path,
        model: str = "zai/glm-5.1",
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
    ) -> AgentHandle:
        """Start a Pi agent in the given worktree."""
        agent_id_file = worktree_path / ".coral_agent_id"
        agent_id = agent_id_file.read_text().strip() if agent_id_file.exists() else "unknown"

        if log_dir is None:
            log_dir = worktree_path / ".pi" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        log_idx = len(list(log_dir.glob(f"{agent_id}*.log")))
        log_path = log_dir / f"{agent_id}.{log_idx}.log"

        if prompt is None:
            if resume_session_id:
                prompt = "Session resumed. Continue where you left off."
                logger.info(f"Resuming agent {agent_id} session {resume_session_id}")
            else:
                prompt = "Begin."

        session_dir = worktree_path / ".pi" / "sessions"
        session_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "pi",
            "--print",
            "--mode",
            "json",
            "--model",
            model,
        ]
        thinking = _pi_thinking_level(runtime_options)
        if thinking:
            cmd.extend(["--thinking", thinking])
        if resume_session_id:
            cmd.extend(["--continue", "--session", resume_session_id])
        cmd.extend([
            "--session-dir",
            str(session_dir),
            "--tools",
            _PI_TOOLS,
        ])
        cmd.append(prompt)

        logger.info(f"Starting Pi agent {agent_id} in {worktree_path}")
        logger.info(f"Command: {' '.join(cmd)}")

        agent_env = _clean_env()
        worktree_venv = str(worktree_path / ".venv")
        agent_env["UV_PROJECT_ENVIRONMENT"] = worktree_venv
        agent_env["VIRTUAL_ENV"] = worktree_venv
        venv_bin = str(worktree_path / ".venv" / "bin")
        agent_env["PATH"] = venv_bin + ":" + agent_env.get("PATH", "")

        if gateway_url:
            agent_env["OPENAI_BASE_URL"] = gateway_url
            logger.info(f"Pi agent {agent_id}: routing via gateway at {gateway_url}")
        if gateway_api_key:
            agent_env["OPENAI_API_KEY"] = gateway_api_key

        log_file = open(log_path, "w", buffering=1)

        err_path: Path | None = None
        err_file: Any = None
        stderr_target: Any = subprocess.STDOUT
        opened = open_agent_stderr_for_log_dir(log_dir, agent_id)
        if opened is not None:
            err_path, err_file = opened
            stderr_target = err_file

        write_coral_log_entry(
            log_file,
            prompt=prompt,
            source=prompt_source or ("restart" if resume_session_id else "start"),
            agent_id=agent_id,
            session_id=resume_session_id,
            task_name=task_name,
            task_description=task_description,
        )

        if verbose:
            process = subprocess.Popen(
                cmd,
                cwd=str(worktree_path),
                stdout=subprocess.PIPE,
                stderr=stderr_target,
                start_new_session=True,
                env=agent_env,
            )

            def _tee_output(proc: subprocess.Popen, log_f, agent: str) -> None:
                try:
                    assert proc.stdout is not None
                    for line in iter(proc.stdout.readline, b""):
                        decoded = line.decode("utf-8", errors="replace")
                        sys.stdout.write(f"[{agent}] {decoded}")
                        sys.stdout.flush()
                        log_f.write(decoded)
                        log_f.flush()
                except Exception as e:
                    logger.error(f"Tee thread error: {e}")
                finally:
                    log_f.close()
                    if proc.stdout:
                        try:
                            proc.stdout.close()
                        except Exception:
                            pass

            tee_thread = threading.Thread(
                target=_tee_output,
                args=(process, log_file, agent_id),
                daemon=True,
            )
            tee_thread.start()
            log_file_ref = None
        else:
            process = subprocess.Popen(
                cmd,
                cwd=str(worktree_path),
                stdout=log_file,
                stderr=stderr_target,
                start_new_session=True,
                env=agent_env,
            )
            log_file_ref = log_file

        logger.info(f"Pi agent {agent_id} started with PID {process.pid}")

        return AgentHandle(
            agent_id=agent_id,
            process=process,
            worktree_path=worktree_path,
            log_path=log_path,
            session_id=resume_session_id,
            err_file=err_file,
            err_path=err_path,
            _log_file=log_file_ref,
        )


def _pi_thinking_level(runtime_options: dict[str, Any] | None) -> str | None:
    """Return the Pi thinking level from runtime options."""
    if not runtime_options:
        return None
    value = runtime_options.get("thinking")
    if value is None:
        value = runtime_options.get("model_reasoning_effort")
    if value is None:
        return None
    return str(value)
