"""Eval implementation: git-add, git-commit, grade, write attempt JSON, print score."""

from __future__ import annotations

import logging
import multiprocessing
import subprocess
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coral.config import CoralConfig
from coral.grader.loader import load_grader
from coral.hub.attempts import get_agent_attempts, write_attempt
from coral.types import Attempt, Task

logger = logging.getLogger(__name__)


def _git_add_and_commit(message: str, workdir: str) -> str:
    """Stage all changes and commit. Returns the new commit hash."""
    # Stage all changes
    result = subprocess.run(
        ["git", "add", "-A"],
        capture_output=True, text=True, cwd=workdir,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git add failed: {result.stderr}")

    # Check if there's anything to commit
    status = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        capture_output=True, cwd=workdir,
    )
    if status.returncode == 0:
        raise RuntimeError("Nothing to commit — no changes detected.")

    # Commit
    result = subprocess.run(
        ["git", "commit", "-m", message],
        capture_output=True, text=True, cwd=workdir,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git commit failed: {result.stderr}")

    # Get the commit hash
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, cwd=workdir,
    )
    return result.stdout.strip()


def _get_parent_hash(commit_hash: str, cwd: str) -> str | None:
    """Get the parent commit hash."""
    result = subprocess.run(
        ["git", "log", "--format=%P", "-n", "1", commit_hash],
        capture_output=True, text=True, cwd=cwd,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().split()[0]
    return None


def _increment_eval_count(coral_dir: Path) -> int:
    """Increment and return the eval counter for this run."""
    counter_file = coral_dir / "public" / "eval_count"
    count = 0
    if counter_file.exists():
        try:
            count = int(counter_file.read_text().strip())
        except ValueError:
            pass
    count += 1
    counter_file.write_text(str(count))
    return count


def _grader_worker(config_path: str, coral_dir: str, codebase_path: str, tasks: list, result_queue):
    """Run grader.grade() in a child process. Puts result or exception into queue.

    Re-loads the grader from config inside the child to avoid pickling
    dynamically-imported modules across process boundaries.
    """
    import asyncio
    try:
        config = CoralConfig.from_yaml(config_path)
        grader = load_grader(config, coral_dir=coral_dir)
        result = asyncio.run(grader.grade(codebase_path, tasks))
        result_queue.put(("ok", result))
    except Exception as e:
        result_queue.put(("error", e, traceback.format_exc()))


def _run_grader_with_timeout(config_path: str, coral_dir: str, codebase_path: str, tasks: list, timeout: int):
    """Run grader in a separate process with a hard timeout.

    Uses multiprocessing so we can kill blocking synchronous code (numpy, etc.)
    that asyncio.wait_for can't interrupt. The grader is re-loaded from config
    inside the child process to avoid pickle issues with dynamic imports.
    """
    if timeout <= 0:
        # No timeout — run directly
        import asyncio
        config = CoralConfig.from_yaml(config_path)
        grader = load_grader(config, coral_dir=coral_dir)
        return asyncio.run(grader.grade(codebase_path, tasks))

    result_queue: multiprocessing.Queue = multiprocessing.Queue()
    proc = multiprocessing.Process(
        target=_grader_worker,
        args=(config_path, coral_dir, codebase_path, tasks, result_queue),
    )
    try:
        proc.start()
        proc.join(timeout=timeout)

        if proc.is_alive():
            # Timed out — kill the process
            proc.kill()
            proc.join(timeout=5)
            raise TimeoutError(f"Grader timed out after {timeout}s")

        if result_queue.empty():
            raise RuntimeError("Grader process exited without returning a result")

        status, *payload = result_queue.get_nowait()
        if status == "ok":
            return payload[0]
        else:
            # Re-raise the exception from the child process
            exc, tb_str = payload
            raise RuntimeError(f"Grader failed: {exc}\n{tb_str}")
    finally:
        result_queue.close()
        result_queue.join_thread()
        proc.close()


def _find_coral_dir(workdir: Path) -> Path | None:
    """Find the shared .coral directory from the .coral_dir breadcrumb file."""
    coral_dir_file = workdir / ".coral_dir"
    if coral_dir_file.exists():
        try:
            return Path(coral_dir_file.read_text().strip()).resolve()
        except (OSError, ValueError):
            pass
    return None


def run_eval(message: str, agent_id: str, workdir: str = ".") -> Attempt:
    """Stage changes, commit with message, run evaluation, and return an Attempt record.

    This is the core of `coral eval -m "description"`.
    """

    workdir_path = Path(workdir).resolve()

    # Find .coral directory by walking up from the worktree.
    # Layout: results/<task>/<timestamp>/.coral/ with worktrees under
    # results/<task>/<timestamp>/agents/<agent-id>/
    coral_dir = _find_coral_dir(workdir_path)
    if coral_dir is None:
        raise FileNotFoundError(f"No .coral directory found from {workdir_path}")

    # Load config
    config_path = coral_dir / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"No config.yaml found at {config_path}")
    config = CoralConfig.from_yaml(config_path)

    # Git add + commit
    commit_hash = _git_add_and_commit(message, str(workdir_path))
    parent_hash = _get_parent_hash(commit_hash, str(workdir_path))

    # Create task from config
    task = Task(
        id=config.task.name,
        name=config.task.name,
        description=config.task.description,
        metadata={"files": config.task.files},
    )

    # Run evaluation with timeout
    eval_timeout = config.grader.timeout  # 0 = no limit

    try:
        result = _run_grader_with_timeout(str(config_path), str(coral_dir), str(workdir_path), [task], eval_timeout)
        score = result.aggregated
        # Build feedback from bundle-level feedback + per-score explanations
        parts = []
        if result.feedback:
            parts.append(result.feedback)
        if result.scores:
            for name, s in result.scores.items():
                if s.explanation:
                    parts.append(f"{name}: {s.explanation}")
        feedback = "\n".join(parts)
        # score is None when grader returns fail() — treat as crashed
        if score is None:
            status = "crashed"
        else:
            # Compare against this agent's previous best score
            prev_attempts = get_agent_attempts(str(coral_dir), agent_id)
            prev_scores = [a.score for a in prev_attempts if a.score is not None]
            minimize = config.grader.direction == "minimize"
            if minimize:
                prev_best = min(prev_scores) if prev_scores else None
            else:
                prev_best = max(prev_scores) if prev_scores else None
            if prev_best is None:
                status = "improved"
            elif minimize and score < prev_best:
                status = "improved"
            elif not minimize and score > prev_best:
                status = "improved"
            elif score == prev_best:
                status = "baseline"
            else:
                status = "regressed"
    except TimeoutError:
        logger.error(f"Evaluation timed out after {eval_timeout}s")
        score = None
        status = "timeout"
        feedback = f"Eval timed out after {eval_timeout}s."
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        score = None
        status = "crashed"
        feedback = str(e)

    # Create attempt record
    attempt = Attempt(
        commit_hash=commit_hash,
        agent_id=agent_id,
        title=message,
        score=score,
        status=status,
        parent_hash=parent_hash,
        timestamp=datetime.now(UTC).isoformat(),
        feedback=feedback,
    )

    # Write to shared state
    write_attempt(str(coral_dir), attempt)

    # Track eval count
    eval_count = _increment_eval_count(coral_dir)
    attempt._eval_count = eval_count  # type: ignore[attr-defined]

    return attempt
