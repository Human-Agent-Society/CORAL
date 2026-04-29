"""Helpers shared by all builtin runtimes for spawning agent subprocesses.

Centralizes the per-agent stderr capture so each runtime does not duplicate
the path-derivation logic and so all four runtimes write to the same
operator-visible location: `<coral_dir>/public/diagnostics/<agent_id>/agent.err`.

This file is intentionally narrow — it is *not* a general process abstraction.
Callers still own the subprocess.Popen invocation, the stdout file handle,
and the lifecycle of every handle returned here. Putting these helpers in a
shared module avoids the four near-identical copies that would otherwise live
in `coral/agent/builtin/{claude_code,codex,opencode,kiro}.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import IO


def derive_coral_dir(log_dir: Path) -> Path | None:
    """Derive the coral_dir from a log_dir following the manager's convention.

    The manager always passes `log_dir = coral_dir / public / logs` to runtime
    `start(...)` calls. Worktree-local fallback paths (e.g. `worktree/.claude/logs`)
    are used only by tests or direct API users; in those cases this returns None
    and the caller should fall back to a sibling-of-log_dir layout.
    """
    if log_dir.name == "logs" and log_dir.parent.name == "public":
        return log_dir.parent.parent
    return None


def open_agent_stderr_file(coral_dir: Path, agent_id: str) -> tuple[Path, IO]:
    """Open (or create) the per-agent stderr capture file in append mode.

    Returns the path and an open file handle. The caller is responsible for
    closing the handle (typically by attaching it to AgentHandle.err_file
    so AgentHandle.stop() closes it).

    Append mode is intentional: across restart cycles, we keep accumulating
    stderr lines into the same file so the most recent fault dump can pull
    a consistent tail. The fault dump itself writes its own header on each
    pause cycle, which is the human-readable separator.
    """
    diag_dir = coral_dir / "public" / "diagnostics" / agent_id
    diag_dir.mkdir(parents=True, exist_ok=True)
    err_path = diag_dir / "agent.err"
    err_file: IO = open(err_path, "a", buffering=1, encoding="utf-8", errors="replace")
    return err_path, err_file


def open_agent_stderr_for_log_dir(log_dir: Path, agent_id: str) -> tuple[Path, IO] | None:
    """Convenience: derive coral_dir from log_dir, then open the stderr file.

    Returns None when the log_dir does not match the manager's convention,
    so callers can fall back to legacy `stderr=subprocess.STDOUT` for tests
    or other non-managed contexts.
    """
    coral_dir = derive_coral_dir(log_dir)
    if coral_dir is None:
        return None
    return open_agent_stderr_file(coral_dir, agent_id)
