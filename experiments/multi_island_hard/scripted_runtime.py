"""Minimal command runtime for controlled end-to-end experiment policies."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any

from coral.agent.process import open_agent_stderr_for_log_dir
from coral.agent.runtime import (
    AgentHandle,
    apply_run_as_user,
    apply_sandbox,
    apply_sandbox_env,
    write_coral_log_entry,
)
from coral.sandbox.protocol import AgentSandboxSpec
from coral.workspace.repo import _clean_env


class ScriptedRuntime:
    """Run a task-provided argv instead of invoking a language model."""

    @property
    def instruction_filename(self) -> str:
        return "AGENTS.md"

    @property
    def shared_dir_name(self) -> str:
        return ".scripted"

    def extract_session_id(self, log_path: Path) -> None:
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
        model: str = "scripted",
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
        sandbox: AgentSandboxSpec | None = None,
    ) -> AgentHandle:
        del coral_md_path, model, max_turns, verbose, gateway_url, gateway_api_key
        agent_file = worktree_path / ".coral_agent_id"
        agent_id = agent_file.read_text().strip() if agent_file.is_file() else "unknown"
        options = runtime_options or {}
        configured = options.get("command")
        if isinstance(configured, str):
            command = shlex.split(configured)
        elif isinstance(configured, (list, tuple)) and all(
            isinstance(item, str) for item in configured
        ):
            command = list(configured)
        else:
            raise ValueError("scripted runtime requires runtime_options.command argv")
        if not command:
            raise ValueError("scripted runtime command cannot be empty")

        if log_dir is None:
            log_dir = worktree_path / self.shared_dir_name / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_index = len(list(log_dir.glob(f"{agent_id}*.log")))
        log_path = log_dir / f"{agent_id}.{log_index}.log"
        log_file = log_path.open("w", buffering=1)
        write_coral_log_entry(
            log_file,
            prompt=prompt or "Run the registered scripted policy.",
            source=prompt_source or ("restart" if resume_session_id else "start"),
            agent_id=agent_id,
            task_name=task_name,
            task_description=task_description,
        )

        environment = _clean_env()
        worktree_venv = str(worktree_path / ".venv")
        environment["UV_PROJECT_ENVIRONMENT"] = worktree_venv
        environment["VIRTUAL_ENV"] = worktree_venv
        environment["PATH"] = (
            str(worktree_path / ".venv" / "bin") + ":" + environment.get("PATH", "")
        )
        apply_sandbox_env(environment, sandbox)
        user_kwargs = apply_run_as_user(environment, run_as_user)
        command = apply_sandbox(command, sandbox)

        err_path: Path | None = None
        err_file: Any = None
        stderr_target: Any = subprocess.STDOUT
        opened = open_agent_stderr_for_log_dir(log_dir, agent_id)
        if opened is not None:
            err_path, err_file = opened
            stderr_target = err_file
        process = subprocess.Popen(
            command,
            cwd=str(worktree_path),
            stdout=log_file,
            stderr=stderr_target,
            start_new_session=True,
            env=environment,
            **user_kwargs,
        )
        return AgentHandle(
            agent_id=agent_id,
            process=process,
            worktree_path=worktree_path,
            log_path=log_path,
            session_id=None,
            _log_file=log_file,
            err_file=err_file,
            err_path=err_path,
        )
