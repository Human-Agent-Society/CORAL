"""Git repo cloning, seeding, and setup commands."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _clean_env() -> dict[str, str]:
    """Return a copy of the environment with venv and IDE variables removed.

    This prevents CORAL's own venv from leaking into subprocesses
    (setup commands, agent spawning) that should use project-local venvs.

    Also strips VS Code Remote SSH IPC variables — these reference
    session-specific Unix sockets that may no longer exist after a
    reconnect/restart, causing ENOENT errors in Node.js subprocesses.
    """
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    for key in list(env):
        if key.startswith("VSCODE_"):
            env.pop(key)
    return env


def clone_or_init_repo(source: Path, dest: Path) -> Path:
    """Clone source repo to dest, or init a new one if source doesn't exist.

    Uses git clone with --no-hardlinks so the clone is fully independent.
    Returns the path to the cloned repo.
    """
    if (source / ".git").exists():
        logger.info(f"Cloning {source} -> {dest}")
        result = subprocess.run(
            ["git", "clone", "--no-hardlinks", str(source), str(dest)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed: {result.stderr}")
        logger.debug(f"Clone: {result.stdout.strip()}")
        return dest

    if source.name.endswith(".git"):
        # Bare repo — clone it
        logger.info(f"Cloning bare repo {source} -> {dest}")
        result = subprocess.run(
            ["git", "clone", str(source), str(dest)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed: {result.stderr}")
        return dest

    # No git repo at source — init a fresh one at dest
    logger.info(f"No git repo at {source}, initializing fresh repo at {dest}")
    dest.mkdir(parents=True, exist_ok=True)

    # Copy source files if the directory has content
    if source.exists() and any(source.iterdir()):
        for item in source.iterdir():
            dst = dest / item.name
            if item.is_dir():
                shutil.copytree(item, dst)
            else:
                shutil.copy2(item, dst)

    subprocess.run(
        ["git", "init", str(dest)],
        capture_output=True, text=True, check=True,
    )
    subprocess.run(
        ["git", "-C", str(dest), "config", "user.email", "coral@local"],
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(dest), "config", "user.name", "CORAL"],
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(dest), "add", "-A"],
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(dest), "commit", "--allow-empty", "-m", "Initial commit"],
        capture_output=True,
    )
    return dest


def copy_eval_to_private(task_dir: Path, coral_dir: Path) -> None:
    """Copy task's eval/ directory to .coral/private/eval/ (hidden from agents).

    This is where grader.py and any test data / answer keys live.
    """
    eval_src = task_dir / "eval"
    if not eval_src.is_dir():
        return

    eval_dst = coral_dir / "private" / "eval"
    if eval_dst.exists():
        shutil.rmtree(eval_dst)
    shutil.copytree(eval_src, eval_dst)
    logger.info(f"Copied eval/ to .coral/private/eval/ ({sum(1 for _ in eval_dst.rglob('*') if _.is_file())} files)")


def copy_seed_directory(seed_dir: Path, repo_dir: Path) -> None:
    """Copy contents of seed/ directory into the repo root.

    Each item inside seed/ is copied to the repo root (not nested under seed/).
    """
    for item in seed_dir.iterdir():
        if item.name == "__pycache__":
            continue
        dst = repo_dir / item.name
        if item.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(item, dst)
            logger.info(f"Seeded directory: {item.name}/")
        else:
            shutil.copy2(item, dst)
            logger.info(f"Seeded file: {item.name}")

    _commit_staged_changes(repo_dir, "Add seed files")


def copy_private_data(private_paths: list[str], coral_dir: Path, config_dir: Path) -> None:
    """Copy private grader data into .coral/ (hidden from agent worktrees).

    Paths are resolved relative to config_dir, same as seed paths.
    Files/dirs are placed under .coral/private/.
    """
    private_dir = coral_dir / "private"
    private_dir.mkdir(parents=True, exist_ok=True)

    for path_str in private_paths:
        src = Path(path_str)
        if not src.is_absolute():
            src = (config_dir / src).resolve()

        if not src.exists():
            logger.warning(f"Private data not found, skipping: {src}")
            continue

        dst = private_dir / src.name
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            logger.info(f"Private data directory: {src.name}/")
        else:
            shutil.copy2(src, dst)
            logger.info(f"Private data file: {src.name}")


def run_setup_commands(
    commands: list[str],
    cwd: Path,
    extra_env: dict[str, str] | None = None,
) -> None:
    """Run setup commands in the given directory.

    Commands are executed sequentially via the shell. If any command fails,
    a RuntimeError is raised with the failing command and stderr.
    """
    env = _clean_env()
    if extra_env:
        env.update(extra_env)

    for cmd in commands:
        logger.info(f"Running setup command: {cmd}")
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Setup command failed (exit {result.returncode}): {cmd}\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )
        if result.stdout.strip():
            logger.debug(f"Setup stdout: {result.stdout.strip()}")


def _commit_staged_changes(repo_dir: Path, message: str) -> None:
    """Stage all changes and commit if there are any."""
    subprocess.run(
        ["git", "-C", str(repo_dir), "add", "-A"],
        capture_output=True,
    )
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "diff", "--cached", "--quiet"],
        capture_output=True,
    )
    if result.returncode != 0:
        subprocess.run(
            ["git", "-C", str(repo_dir), "commit", "-m", message],
            capture_output=True,
        )
        logger.info(f"Committed: {message}")
