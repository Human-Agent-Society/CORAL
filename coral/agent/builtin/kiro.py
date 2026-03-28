"""Kiro CLI subprocess lifecycle."""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from coral.agent.runtime import AgentHandle, write_coral_log_entry
from coral.workspace.repo import _clean_env

logger = logging.getLogger(__name__)


class KiroRuntime:
    """Spawn and manage Kiro CLI agent subprocesses."""

    @property
    def instruction_filename(self) -> str:
        return "KIRO.md"

    @property
    def shared_dir_name(self) -> str:
        return ".kiro"

    def extract_session_id(self, log_path: Path) -> str | None:
        return None  # Kiro doesn't expose session IDs in the same way

    def start(
        self,
        worktree_path: Path,
        coral_md_path: Path,
        model: str = "default",
        runtime_options: dict[str, Any] | None = None,
        max_turns: int = 200,
        log_dir: Path | None = None,
        verbose: bool = False,
        resume_session_id: str | None = None,
        prompt: str | None = None,
        prompt_source: str | None = None,
        task_name: str | None = None,
        task_description: str | None = None,
    ) -> AgentHandle:
        agent_id_file = worktree_path / ".coral_agent_id"
        agent_id = agent_id_file.read_text().strip() if agent_id_file.exists() else "unknown"

        if log_dir is None:
            log_dir = worktree_path / ".kiro" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        log_idx = len(list(log_dir.glob(f"{agent_id}*.log")))
        log_path = log_dir / f"{agent_id}.{log_idx}.log"

        if prompt is None:
            prompt = "Begin."

        cmd = [
            "kiro-cli", "chat",
            prompt,
            "--no-interactive",
            "-a",  # trust all tools
        ]

        if model and model != "default":
            cmd.extend(["--model", model])

        logger.info(f"Starting Kiro agent {agent_id} in {worktree_path}")
        logger.info(f"Command: {' '.join(cmd)}")

        agent_env = _clean_env()

        log_file = open(log_path, "w", buffering=1)

        write_coral_log_entry(
            log_file,
            prompt=prompt,
            source=prompt_source or "start",
            agent_id=agent_id,
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

            def _tee_output(proc, log_f, agent):
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

            tee_thread = threading.Thread(
                target=_tee_output, args=(process, log_file, agent_id), daemon=True
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

        logger.info(f"Kiro agent {agent_id} started with PID {process.pid}")

        return AgentHandle(
            agent_id=agent_id,
            process=process,
            worktree_path=worktree_path,
            log_path=log_path,
            _log_file=log_file_ref,
        )
