"""OpenAI Codex CLI subprocess lifecycle."""

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

_CODEX_RUNTIME_OPTION_KEYS = {
    "model_reasoning_effort",
    "fast_mode",
    "personality",
    "web_search",
}


def _extract_codex_session_id(log_path: Path) -> str | None:
    """Extract session_id from a Codex JSONL log.

    Codex exec --json emits JSONL events. Session IDs appear in events
    with a "session_id" field, typically in the final summary event.
    """
    try:
        lines = log_path.read_text().strip().splitlines()
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


class CodexRuntime:
    """Spawn and manage OpenAI Codex CLI agent subprocesses."""

    @property
    def instruction_filename(self) -> str:
        return "AGENTS.md"

    @property
    def shared_dir_name(self) -> str:
        return ".codex"

    def extract_session_id(self, log_path: Path) -> str | None:
        return _extract_codex_session_id(log_path)

    def start(
        self,
        worktree_path: Path,
        coral_md_path: Path,
        model: str = "gpt-5.4",
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
        """Start a Codex agent in the given worktree.

        Uses `codex exec` for non-interactive operation.
        Resume uses `codex exec resume <session_id> "prompt"`.
        """
        agent_id_file = worktree_path / ".coral_agent_id"
        agent_id = agent_id_file.read_text().strip() if agent_id_file.exists() else "unknown"

        if log_dir is None:
            log_dir = worktree_path / ".codex" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        log_idx = len(list(log_dir.glob(f"{agent_id}*.log")))
        log_path = log_dir / f"{agent_id}.{log_idx}.log"

        if prompt is None:
            if resume_session_id:
                prompt = "Session resumed. Continue where you left off."
                logger.info(f"Resuming agent {agent_id} session {resume_session_id}")
            else:
                prompt = "Begin."

        option_args = _build_codex_runtime_option_args(runtime_options)

        if resume_session_id:
            # codex exec resume <session_id> "follow-up prompt"
            cmd = [
                "codex", "exec",
                "resume", resume_session_id,
                prompt,
                "--dangerously-bypass-approvals-and-sandbox",
                "--model", model,
                *option_args,
                "--json",
            ]
        else:
            # codex exec "prompt"
            cmd = [
                "codex", "exec",
                prompt,
                "--dangerously-bypass-approvals-and-sandbox",
                "--model", model,
                *option_args,
                "--json",
            ]

        logger.info(f"Starting Codex agent {agent_id} in {worktree_path}")
        logger.info(f"Command: {' '.join(cmd)}")

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
                env=_clean_env(),
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
                env=_clean_env(),
            )
            log_file_ref = log_file

        logger.info(f"Codex agent {agent_id} started with PID {process.pid}")

        return AgentHandle(
            agent_id=agent_id,
            process=process,
            worktree_path=worktree_path,
            log_path=log_path,
            session_id=resume_session_id,
            _log_file=log_file_ref,
        )


def _toml_literal(value: Any) -> str:
    """Serialize a scalar value for `codex -c key=value`."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(str(value))


def _build_codex_runtime_option_args(runtime_options: dict[str, Any] | None) -> list[str]:
    """Translate runtime options into `codex exec -c key=value` arguments."""
    if not runtime_options:
        return []

    args: list[str] = []
    for key in sorted(runtime_options):
        if key not in _CODEX_RUNTIME_OPTION_KEYS:
            logger.warning(f"Ignoring unsupported Codex runtime option: {key}")
            continue
        args.extend(["-c", f"{key}={_toml_literal(runtime_options[key])}"])
    return args
