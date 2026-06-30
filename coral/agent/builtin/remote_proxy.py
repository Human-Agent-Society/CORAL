"""Remote proxy runtime backed by a local long-running adapter process."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

from coral.agent.runtime import AgentHandle, apply_run_as_user, write_coral_log_entry
from coral.workspace.repo import _clean_env

logger = logging.getLogger(__name__)


class RemoteProxyRuntime:
    """Run a local proxy process that controls a remote agent runtime."""

    @property
    def instruction_filename(self) -> str:
        return "AGENTS.md"

    @property
    def shared_dir_name(self) -> str:
        return ".remote"

    def extract_session_id(self, log_path: Path) -> str | None:
        return None

    def classify_exit(
        self,
        log_path: Path,
        exit_code: int | None,
        uptime_seconds: float | None,
        min_clean_runtime_seconds: int = 60,
    ) -> str:
        return "clean" if exit_code == 0 else "no_result"

    def start(
        self,
        worktree_path: Path,
        coral_md_path: Path,
        model: str = "remote",
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
    ) -> AgentHandle:
        """Start the local remote-runtime proxy process."""
        runtime_options = runtime_options or {}
        adapter = runtime_options.get("adapter")
        if not adapter:
            raise ValueError("remote_proxy runtime requires runtime_options.adapter")

        adapter_config = dict(runtime_options.get("config") or {})
        sync_interval = float(runtime_options.get("sync_interval_seconds", 30))
        if sync_interval <= 0:
            raise ValueError("remote_proxy runtime_options.sync_interval_seconds must be > 0")

        agent_id_file = worktree_path / ".coral_agent_id"
        agent_id = agent_id_file.read_text().strip() if agent_id_file.exists() else "unknown"

        if log_dir is None:
            log_dir = worktree_path / ".remote" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        log_idx = len(list(log_dir.glob(f"{agent_id}*.log")))
        log_path = log_dir / f"{agent_id}.{log_idx}.log"

        if prompt is None:
            prompt = "Start or resume this CORAL task through the configured remote runtime."

        state_dir = self._remote_state_dir(worktree_path)
        cmd = [
            sys.executable,
            "-m",
            "coral.agent.remote_proxy_worker",
            "--adapter",
            str(adapter),
            "--config-json",
            json.dumps(adapter_config),
            "--agent-id",
            agent_id,
            "--worktree-path",
            str(worktree_path),
            "--state-dir",
            str(state_dir),
            "--log-path",
            str(log_path),
            "--prompt",
            prompt,
            "--task-name",
            task_name or "",
            "--task-description",
            task_description or "",
            "--sync-interval-seconds",
            str(sync_interval),
        ]

        logger.info("Starting remote proxy agent %s in %s", agent_id, worktree_path)
        logger.info("Adapter: %s", adapter)

        agent_env = _clean_env()
        worktree_venv = str(worktree_path / ".venv")
        agent_env["UV_PROJECT_ENVIRONMENT"] = worktree_venv
        agent_env["VIRTUAL_ENV"] = worktree_venv
        agent_env["PATH"] = str(worktree_path / ".venv" / "bin") + ":" + agent_env.get("PATH", "")

        user_kwargs = apply_run_as_user(agent_env, run_as_user)
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

        process = subprocess.Popen(
            cmd,
            cwd=str(worktree_path),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=agent_env,
            **user_kwargs,
        )

        logger.info("Remote proxy agent %s started with PID %s", agent_id, process.pid)
        return AgentHandle(
            agent_id=agent_id,
            process=process,
            worktree_path=worktree_path,
            log_path=log_path,
            session_id=resume_session_id,
            _log_file=log_file,
        )

    @staticmethod
    def _remote_state_dir(worktree_path: Path) -> Path:
        coral_dir_file = worktree_path / ".coral_dir"
        if coral_dir_file.exists():
            return Path(coral_dir_file.read_text().strip()) / "public" / "remote_state"
        return worktree_path / ".coral" / "public" / "remote_state"
