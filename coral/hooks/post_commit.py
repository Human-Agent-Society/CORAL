"""Eval implementation: git-add, git-commit, queue for grading, write attempt JSON, print score."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from coral.config import CoralConfig
from coral.hub.attempts import get_agent_attempts, write_attempt
from coral.hub.checkpoint import checkpoint
from coral.queue.client import QueueClient
from coral.queue.counter import increment_eval_count
from coral.types import Attempt

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


def _run_eval_via_queue(
    config: CoralConfig,
    coral_dir: Path,
    agent_id: str,
    commit_hash: str,
    config_path: str,
    codebase_path: str,
) -> tuple[float | None, str, str]:
    """Submit eval request to the queue and wait for a result."""
    client = QueueClient(coral_dir, config.grader.queue, grader_timeout=config.grader.timeout)
    request = client.submit(agent_id, commit_hash, config_path, codebase_path)
    position = client.get_position(request.ticket_id)
    print(f"Eval queued (position {position}, ticket {request.ticket_id[:8]})")

    try:
        eval_result = client.wait_for_result(request.ticket_id)
    except TimeoutError:
        logger.error("Queue timeout waiting for eval result")
        return None, "Timed out waiting for eval result from queue.", "timeout"

    if eval_result.status == "error":
        logger.error(f"Queue eval failed: {eval_result.error}")
        return None, eval_result.error, "crashed"

    if eval_result.status == "timeout":
        return None, eval_result.error or "Grader timed out.", "timeout"

    score = eval_result.score
    feedback = eval_result.feedback

    if score is None:
        return score, feedback, "crashed"

    # Compare against previous best
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
    return score, feedback, status


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
    """Stage changes, commit with message, submit to eval queue, and return an Attempt record.

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

    # Submit to queue and wait for result
    score, feedback, status = _run_eval_via_queue(
        config, coral_dir, agent_id, commit_hash, str(config_path), str(workdir_path),
    )

    # Look up parent attempt's shared state hash
    parent_shared_state_hash = None
    if parent_hash:
        parent_attempt_file = coral_dir / "public" / "attempts" / f"{parent_hash}.json"
        if parent_attempt_file.exists():
            try:
                parent_data = json.loads(parent_attempt_file.read_text())
                parent_shared_state_hash = parent_data.get("shared_state_hash")
            except (json.JSONDecodeError, OSError):
                pass

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
        parent_shared_state_hash=parent_shared_state_hash,
    )

    # Checkpoint shared state and record the hash
    attempt.shared_state_hash = checkpoint(str(coral_dir), agent_id, message)

    # Write to shared state
    write_attempt(str(coral_dir), attempt)

    # Track eval count
    eval_count = increment_eval_count(coral_dir)
    attempt._eval_count = eval_count  # type: ignore[attr-defined]

    return attempt
