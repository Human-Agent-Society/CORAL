"""Checkpoint shared state in .coral/public/ using a local git repo."""

from __future__ import annotations

import fcntl
import logging
import subprocess
from pathlib import Path

from coral.hub._island import island_root

logger = logging.getLogger(__name__)


def _checkpoint_dir(coral_dir: str, island_id: str | int | None = None) -> Path:
    """The directory the checkpoint repo lives in (public/ or islands/<id>/)."""
    return island_root(coral_dir, island_id)


def init_checkpoint_repo(coral_dir: str, island_id: str | int | None = None) -> None:
    """Initialize a git repo inside the island root for shared state tracking.

    Idempotent — skips if .git already exists.
    """
    root = _checkpoint_dir(coral_dir, island_id)
    root.mkdir(parents=True, exist_ok=True)
    if (root / ".git").exists():
        return

    try:
        subprocess.run(
            ["git", "init"],
            cwd=str(root),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "coral"],
            cwd=str(root),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "coral@local"],
            cwd=str(root),
            capture_output=True,
            check=True,
        )
        gitignore = root / ".gitignore"
        gitignore.write_text("coral.lock\n")
        subprocess.run(
            ["git", "add", "-A"],
            cwd=str(root),
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "init: shared state tracking"],
            cwd=str(root),
            capture_output=True,
            check=True,
        )
        logger.info("Initialized checkpoint repo in %s", root)
    except Exception:
        logger.warning("Failed to initialize checkpoint repo", exc_info=True)


def checkpoint(
    coral_dir: str,
    agent_id: str,
    message: str,
    island_id: str | int | None = None,
) -> str | None:
    """Commit all changes in the island root and return the commit hash, or None.

    Acquires a file lock for concurrency safety. Never raises — logs warnings.
    """
    root = _checkpoint_dir(coral_dir, island_id)

    # Lazy-init for backward compat with runs started before checkpointing
    if not (root / ".git").exists():
        init_checkpoint_repo(coral_dir, island_id)

    lock_path = root / ".git" / "coral.lock"
    try:
        lock_path.touch(exist_ok=True)
        with open(lock_path) as lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

            subprocess.run(
                ["git", "add", "-A"],
                cwd=str(root),
                capture_output=True,
                check=True,
            )

            # Check if there are staged changes
            result = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=str(root),
                capture_output=True,
            )
            if result.returncode == 0:
                return None  # nothing to commit

            commit_msg = f"checkpoint: {agent_id} - {message}"
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=str(root),
                capture_output=True,
                check=True,
            )

            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
    except Exception:
        logger.warning("Checkpoint failed", exc_info=True)
        return None


def checkpoint_history(
    coral_dir: str,
    count: int = 20,
    island_id: str | int | None = None,
) -> list[dict[str, str]]:
    """Return recent checkpoint entries as list of {hash, date, message} dicts.

    With ``island_id=None`` in multi-island mode, merges history from every
    island so ``coral notes --history`` shows the whole team's checkpoints.
    Each entry is tagged with ``island_id`` for traceability.
    """
    coral_dir_path = Path(coral_dir)
    if island_id is not None or not (coral_dir_path / "islands").exists():
        return _checkpoint_history_single(coral_dir, count, island_id)

    from coral.hub._island import all_view_roots

    merged: list[dict[str, str]] = []
    for view_root in all_view_roots(coral_dir):
        sub = _checkpoint_history_single(coral_dir, count, island_id=view_root.name)
        for entry in sub:
            entry["island_id"] = view_root.name
        merged.extend(sub)
    # Sort newest-first by parsed date, then take the top `count`.
    merged.sort(key=lambda e: e.get("date", ""), reverse=True)
    return merged[:count]


def _checkpoint_history_single(
    coral_dir: str,
    count: int,
    island_id: str | int | None,
) -> list[dict[str, str]]:
    root = _checkpoint_dir(coral_dir, island_id)
    if not (root / ".git").exists():
        return []

    try:
        result = subprocess.run(
            ["git", "log", "--format=%H|%ai|%s", f"-n{count}"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        )
        entries = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) == 3:
                entries.append(
                    {
                        "hash": parts[0],
                        "date": parts[1],
                        "message": parts[2],
                    }
                )
        return entries
    except Exception:
        logger.warning("Failed to read checkpoint history", exc_info=True)
        return []


def checkpoint_diff(
    coral_dir: str,
    commit_hash: str,
    island_id: str | int | None = None,
) -> str:
    """Return the stat+patch output for a specific checkpoint commit."""
    coral_dir_path = Path(coral_dir)
    if island_id is None and (coral_dir_path / "islands").exists():
        from coral.hub._island import all_view_roots

        outputs: list[str] = []
        for view_root in all_view_roots(coral_dir_path):
            if not (view_root / ".git").exists():
                continue
            exists = subprocess.run(
                ["git", "cat-file", "-e", f"{commit_hash}^{{commit}}"],
                cwd=str(view_root),
                capture_output=True,
                text=True,
            )
            if exists.returncode != 0:
                continue
            diff = checkpoint_diff(coral_dir, commit_hash, island_id=view_root.name)
            outputs.append(f"Island {view_root.name}\n{'=' * 72}\n{diff}")
        if outputs:
            return "\n".join(outputs)
        return f"Failed to show commit {commit_hash}: commit not found in any island."

    root = _checkpoint_dir(coral_dir, island_id)
    if not (root / ".git").exists():
        return "No checkpoint repo found."

    try:
        result = subprocess.run(
            ["git", "show", "--stat", "--patch", commit_hash],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Failed to show commit {commit_hash}: {e.stderr}"
    except Exception as e:
        return f"Error: {e}"
