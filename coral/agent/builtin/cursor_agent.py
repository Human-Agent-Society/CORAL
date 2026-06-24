"""Cursor Agent CLI subprocess lifecycle.

Wraps the official `cursor-agent` headless CLI. Argv shape and stream-json
event schema are taken from Cursor's published headless docs and confirmed
against the cursor-acp reference implementation
(https://github.com/raphaelluethy/cursor-acp, src/cursor-cli-runner.ts and
src/cursor-event-mapper.ts).

The CLI emits NDJSON events on stdout; the first event is
`{"type":"system","subtype":"init","session_id":"..."}` which is what we
extract for resume. Approval prompts are bypassed with --force (required
for any write tool to run in --print mode).
"""

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
from coral.agent.runtime import AgentHandle, apply_run_as_user, write_coral_log_entry
from coral.workspace.repo import _clean_env

logger = logging.getLogger(__name__)

# Keys allowed inside `agents.runtime_options` for the cursor_agent runtime.
# `command` overrides the binary name (default `cursor-agent`); `mode`
# corresponds to the CLI's `--mode plan|ask` flag; `stream_partial_output`
# toggles the matching boolean flag.
_CURSOR_RUNTIME_OPTION_KEYS = {
    "command",
    "mode",
    "stream_partial_output",
}


def _extract_cursor_session_id(log_path: Path) -> str | None:
    """Extract session_id from a cursor-agent stream-json log.

    The CLI emits `{"type":"system","subtype":"init","session_id":"..."}`
    as its first event. We scan from the end first (resumed sessions can
    re-emit init), falling back to any line carrying a `session_id`.
    """
    try:
        lines = log_path.read_text().strip().splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                data.get("type") == "system"
                and data.get("subtype") == "init"
                and data.get("session_id")
            ):
                return data["session_id"]
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = data.get("session_id")
            if sid:
                return sid
    except Exception as e:
        logger.debug(f"Failed to extract session_id from {log_path}: {e}")
    return None


class CursorAgentRuntime:
    """Spawn and manage Cursor Agent CLI subprocesses."""

    @property
    def instruction_filename(self) -> str:
        # cursor-agent reads AGENTS.md (and CLAUDE.md) at the workspace root
        # per Cursor's CLI docs. AGENTS.md is the cross-vendor convention also
        # used by the codex runtime.
        return "AGENTS.md"

    @property
    def shared_dir_name(self) -> str:
        return ".cursor"

    def extract_session_id(self, log_path: Path) -> str | None:
        return _extract_cursor_session_id(log_path)

    def classify_exit(
        self,
        log_path: Path,
        exit_code: int | None,
        uptime_seconds: float | None,
        min_clean_runtime_seconds: int = 60,
    ) -> str:
        """Classify a cursor-agent exit using the uptime fallback.

        The CLI does emit a `{"type":"result"}` terminal event, but there is
        an outstanding upstream bug where `--print` mode can hang and never
        flush a result line; gating clean status on uptime is therefore
        safer than scanning for the marker.
        """
        return classify_by_uptime(exit_code, uptime_seconds, min_clean_runtime_seconds)

    def start(
        self,
        worktree_path: Path,
        coral_md_path: Path,
        model: str = "auto",
        runtime_options: dict[str, Any] | None = None,
        max_turns: int = 0,
        log_dir: Path | None = None,
        verbose: bool = False,
        resume_session_id: str | None = None,
        prompt: str | None = None,
        prompt_source: str | None = None,
        task_name: str | None = None,
        task_description: str | None = None,
        # Gateway routing is not wired up for cursor-agent — the CLI uses
        # Cursor's own auth (`cursor-agent login`) and does not honour the
        # OpenAI/Anthropic base-url env vars LiteLLM relies on. Accept the
        # kwargs so the manager can keep a uniform call signature.
        gateway_url: str | None = None,
        gateway_api_key: str | None = None,
        run_as_user: dict[str, Any] | None = None,
    ) -> AgentHandle:
        agent_id_file = worktree_path / ".coral_agent_id"
        agent_id = agent_id_file.read_text().strip() if agent_id_file.exists() else "unknown"

        if log_dir is None:
            log_dir = worktree_path / ".cursor" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        log_idx = len(list(log_dir.glob(f"{agent_id}*.log")))
        log_path = log_dir / f"{agent_id}.{log_idx}.log"

        if prompt is None:
            if resume_session_id:
                prompt = "Session resumed. Continue evolving your solutions where you left off. There is no user in the loop — make decisions, run evals, accumulate knowledge, and iterate without waiting for input."
                logger.info(f"Resuming agent {agent_id} session {resume_session_id}")
            else:
                prompt = "Begin working on your task and iterating on the seed solution. There is no user in the loop — make decisions, run evals, accumulate knowledge, and iterate without waiting for input."

        opts = runtime_options or {}
        for key in opts:
            if key not in _CURSOR_RUNTIME_OPTION_KEYS:
                logger.warning(f"Ignoring unsupported cursor_agent runtime option: {key}")

        binary = str(opts.get("command") or "cursor-agent")

        cmd: list[str] = [
            binary,
            "--print",
            "--output-format",
            "stream-json",
            "--force",
            "--workspace",
            str(worktree_path),
        ]

        if model and model != "auto":
            cmd.extend(["--model", model])

        mode = opts.get("mode")
        if mode:
            cmd.extend(["--mode", str(mode)])

        if opts.get("stream_partial_output"):
            cmd.append("--stream-partial-output")

        if resume_session_id:
            cmd.extend(["--resume", resume_session_id])

        # Prompt is positional and goes last, mirroring the cursor-acp
        # reference impl (cursor-cli-runner.ts L106-L129).
        cmd.append(prompt)

        logger.info(f"Starting Cursor agent {agent_id} in {worktree_path}")
        logger.info(f"Command: {' '.join(cmd)}")

        agent_env = _clean_env()
        worktree_venv = str(worktree_path / ".venv")
        agent_env["UV_PROJECT_ENVIRONMENT"] = worktree_venv
        agent_env["VIRTUAL_ENV"] = worktree_venv
        venv_bin = str(worktree_path / ".venv" / "bin")
        agent_env["PATH"] = venv_bin + ":" + agent_env.get("PATH", "")

        # OS-user isolation: drop the agent subprocess to the unprivileged
        # user (no-op when run_as_user is None). Sets HOME so the CLI finds
        # its creds in the agent's home; returns Popen user=/group= kwargs.
        user_kwargs = apply_run_as_user(agent_env, run_as_user)

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
                **user_kwargs,
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
                **user_kwargs,
            )
            log_file_ref = log_file

        logger.info(f"Cursor agent {agent_id} started with PID {process.pid}")

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
