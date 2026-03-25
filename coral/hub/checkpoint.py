"""Checkpoint shared state in .coral/public/ using a local git repo."""

from __future__ import annotations

import fcntl
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _public_dir(coral_dir: str) -> Path:
    return Path(coral_dir) / "public"


def init_checkpoint_repo(coral_dir: str) -> None:
    """Initialize a git repo inside .coral/public/ for shared state tracking.

    Idempotent — skips if .git already exists.
    """
    public = _public_dir(coral_dir)
    if (public / ".git").exists():
        return

    try:
        subprocess.run(
            ["git", "init"],
            cwd=str(public), capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "coral"],
            cwd=str(public), capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "coral@local"],
            cwd=str(public), capture_output=True, check=True,
        )
        gitignore = public / ".gitignore"
        gitignore.write_text("coral.lock\n")
        subprocess.run(
            ["git", "add", "-A"],
            cwd=str(public), capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "init: shared state tracking"],
            cwd=str(public), capture_output=True, check=True,
        )
        logger.info("Initialized checkpoint repo in %s", public)
    except Exception:
        logger.warning("Failed to initialize checkpoint repo", exc_info=True)


def checkpoint(coral_dir: str, agent_id: str, message: str) -> str | None:
    """Commit all changes in .coral/public/ and return the commit hash, or None.

    Acquires a file lock for concurrency safety. Never raises — logs warnings.
    """
    public = _public_dir(coral_dir)

    # Lazy-init for backward compat with runs started before checkpointing
    if not (public / ".git").exists():
        init_checkpoint_repo(coral_dir)

    lock_path = public / ".git" / "coral.lock"
    try:
        lock_path.touch(exist_ok=True)
        with open(lock_path) as lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

            subprocess.run(
                ["git", "add", "-A"],
                cwd=str(public), capture_output=True, check=True,
            )

            # Check if there are staged changes
            result = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=str(public), capture_output=True,
            )
            if result.returncode == 0:
                return None  # nothing to commit

            commit_msg = f"checkpoint: {agent_id} - {message}"
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=str(public), capture_output=True, check=True,
            )

            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(public), capture_output=True, text=True, check=True,
            )
            return result.stdout.strip()
    except Exception:
        logger.warning("Checkpoint failed", exc_info=True)
        return None


def checkpoint_history(coral_dir: str, count: int = 20) -> list[dict[str, str]]:
    """Return recent checkpoint entries as list of {hash, date, message} dicts."""
    public = _public_dir(coral_dir)
    if not (public / ".git").exists():
        return []

    try:
        result = subprocess.run(
            ["git", "log", "--format=%H|%ai|%s", f"-n{count}"],
            cwd=str(public), capture_output=True, text=True, check=True,
        )
        entries = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) == 3:
                entries.append({
                    "hash": parts[0],
                    "date": parts[1],
                    "message": parts[2],
                })
        return entries
    except Exception:
        logger.warning("Failed to read checkpoint history", exc_info=True)
        return []


def checkpoint_diff(coral_dir: str, commit_hash: str) -> str:
    """Return the stat+patch output for a specific checkpoint commit."""
    public = _public_dir(coral_dir)
    if not (public / ".git").exists():
        return "No checkpoint repo found."

    try:
        result = subprocess.run(
            ["git", "show", "--stat", "--patch", commit_hash],
            cwd=str(public), capture_output=True, text=True, check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Failed to show commit {commit_hash}: {e.stderr}"
    except Exception as e:
        return f"Error: {e}"
