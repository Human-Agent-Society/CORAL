"""OpenCode CLI subprocess lifecycle."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from coral.agent.runtime import AgentHandle, write_coral_log_entry
from coral.workspace.repo import _clean_env

logger = logging.getLogger(__name__)


def _extract_opencode_session_id(log_path: Path) -> str | None:
    """Extract session_id from an OpenCode JSON log.

    OpenCode `run --format json` emits JSON events. Session IDs appear
    in events with a "session_id" or "sessionId" field.
    """
    try:
        lines = log_path.read_text().strip().splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                sid = data.get("session_id") or data.get("sessionId")
                if sid:
                    return sid
            except json.JSONDecodeError:
                continue
    except Exception as e:
        logger.debug(f"Failed to extract session_id from {log_path}: {e}")
    return None


class OpenCodeRuntime:
    """Spawn and manage OpenCode CLI agent subprocesses.

    Uses `opencode run` for non-interactive operation.
    Resume uses `opencode run --continue --session <id>`.
    """

    @property
    def instruction_filename(self) -> str:
        return "AGENTS.md"

    @property
    def shared_dir_name(self) -> str:
        return ".opencode"

    def extract_session_id(self, log_path: Path) -> str | None:
        return _extract_opencode_session_id(log_path)

    def start(
        self,
        worktree_path: Path,
        coral_md_path: Path,
        model: str = "gpt-5",
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
        """Start an OpenCode agent in the given worktree."""
        agent_id_file = worktree_path / ".coral_agent_id"
        agent_id = agent_id_file.read_text().strip() if agent_id_file.exists() else "unknown"

        if log_dir is None:
            log_dir = worktree_path / ".opencode" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        log_idx = len(list(log_dir.glob(f"{agent_id}*.log")))
        log_path = log_dir / f"{agent_id}.{log_idx}.log"

        if prompt is None:
            if resume_session_id:
                prompt = "Session resumed. Continue where you left off."
                logger.info(f"Resuming agent {agent_id} session {resume_session_id}")
            else:
                prompt = "Begin."

        # Build command: opencode run [flags] <prompt>
        # Keep the full provider/model format (e.g. "minimax/MiniMax-M2.5")
        # so OpenCode knows which provider to use. When the gateway is active,
        # the provider's baseURL is patched in opencode.json to route through
        # the LiteLLM proxy.
        cmd = [
            "opencode", "run",
            "--model", model,
            "--format", "json",
        ]

        if resume_session_id:
            cmd.extend(["--continue", "--session", resume_session_id])

        # Prompt goes last as positional arg
        cmd.append(prompt)

        logger.info(f"Starting OpenCode agent {agent_id} in {worktree_path}")
        logger.info(f"Command: {' '.join(cmd)}")

        agent_env = _clean_env()
        worktree_venv = str(worktree_path / ".venv")
        agent_env["UV_PROJECT_ENVIRONMENT"] = worktree_venv
        # Set VIRTUAL_ENV so login shells (which reset PATH) can restore it
        # via /etc/profile.d/coral-venv.sh in Docker containers.
        agent_env["VIRTUAL_ENV"] = worktree_venv
        # Prepend .venv/bin to PATH for non-login shells
        venv_bin = str(worktree_path / ".venv" / "bin")
        agent_env["PATH"] = venv_bin + ":" + agent_env.get("PATH", "")

        # Route through gateway if configured
        if gateway_url:
            agent_env["OPENAI_BASE_URL"] = gateway_url
            logger.info(f"OpenCode agent {agent_id}: routing via gateway at {gateway_url}")
        if gateway_api_key:
            agent_env["OPENAI_API_KEY"] = gateway_api_key

        log_file = open(log_path, "w", buffering=1)

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
                stderr=subprocess.STDOUT,
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
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=agent_env,
            )
            log_file_ref = log_file

        logger.info(f"OpenCode agent {agent_id} started with PID {process.pid}")

        return AgentHandle(
            agent_id=agent_id,
            process=process,
            worktree_path=worktree_path,
            log_path=log_path,
            session_id=resume_session_id,
            _log_file=log_file_ref,
        )
