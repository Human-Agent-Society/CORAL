"""Claude Code CLI subprocess lifecycle."""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from coral.agent.runtime import AgentHandle, _extract_session_id, write_coral_log_entry
from coral.workspace.repo import _clean_env

logger = logging.getLogger(__name__)


class ClaudeCodeRuntime:
    """Spawn and manage Claude Code agent subprocesses."""

    @property
    def instruction_filename(self) -> str:
        return "CLAUDE.md"

    @property
    def shared_dir_name(self) -> str:
        return ".claude"

    def extract_session_id(self, log_path: Path) -> str | None:
        return _extract_session_id(log_path)

    def start(
        self,
        worktree_path: Path,
        coral_md_path: Path,
        model: str = "opus",
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
        """Start a Claude Code agent in the given worktree."""
        agent_id_file = worktree_path / ".coral_agent_id"
        agent_id = agent_id_file.read_text().strip() if agent_id_file.exists() else "unknown"

        if log_dir is None:
            log_dir = worktree_path / ".claude" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Use numbered log files so we don't overwrite on restart
        log_idx = len(list(log_dir.glob(f"{agent_id}*.log")))
        log_path = log_dir / f"{agent_id}.{log_idx}.log"

        if prompt is None:
            if resume_session_id:
                prompt = "Session resumed. Continue where you left off."
                logger.info(f"Resuming agent {agent_id} session {resume_session_id}")
            else:
                prompt = "Begin."

        cmd = [
            "claude",
            "-p", prompt,
            "--model", model,
            "--max-turns", str(max_turns),
            "--output-format", "stream-json",
            "--verbose",
        ]

        if resume_session_id:
            cmd.extend(["--resume", resume_session_id])

        logger.info(f"Starting agent {agent_id} in {worktree_path}")
        logger.info(f"Command: {' '.join(cmd)}")

        # Give each agent its own venv so concurrent uv operations don't collide
        agent_env = _clean_env()
        agent_env["UV_PROJECT_ENVIRONMENT"] = str(worktree_path / ".venv")

        # Route through gateway if configured
        if gateway_url:
            agent_env["ANTHROPIC_BASE_URL"] = gateway_url
            logger.info(f"Agent {agent_id}: routing via gateway at {gateway_url}")
        if gateway_api_key:
            agent_env["ANTHROPIC_API_KEY"] = gateway_api_key

        log_file = open(log_path, "w", buffering=1)  # line-buffered

        # Write CORAL prompt entry so the initial instruction is captured in the log
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
            # Tee: write to both terminal and log file
            process = subprocess.Popen(
                cmd,
                cwd=str(worktree_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # own process group for clean SIGINT
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
            log_file_ref = None  # thread owns the file now
        else:
            # Background: write stream-json to log file
            process = subprocess.Popen(
                cmd,
                cwd=str(worktree_path),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # own process group for clean SIGINT
                env=agent_env,
            )
            log_file_ref = log_file

        logger.info(f"Agent {agent_id} started with PID {process.pid}")

        return AgentHandle(
            agent_id=agent_id,
            process=process,
            worktree_path=worktree_path,
            log_path=log_path,
            session_id=resume_session_id,
            _log_file=log_file_ref,
        )
