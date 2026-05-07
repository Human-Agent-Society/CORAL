"""Grader daemon: watches .coral/public/attempts/ for pending entries and grades them.

One long-running process per CORAL run. Reuses a single `TaskGrader`
instance across all evals (no per-eval cold start) and grades each attempt
inside an isolated `git worktree add --detach <commit>` checkout, so agent
commits during grading do not perturb the codebase the grader sees.

Design invariants:
- Pending attempts are dispatched through a thread pool of size
  `grader.parallel.max_workers` (default 1 = serial). Bumping the value is
  just configuration; safety is the operator's call — most graders are NOT
  concurrency-safe (Docker port conflicts, GPU contention, shared scratch
  dirs, etc.).
- Writes are atomic via hub.attempts.write_attempt (tmp + rename).
- Daemon is idempotent: re-seeing an already-scored attempt is a no-op.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import shutil
import subprocess
import threading
import time
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coral.config import CoralConfig
from coral.grader.loader import load_grader
from coral.hub.attempts import (
    get_agent_attempts,
    increment_eval_count,
    read_attempts,
    write_attempt,
)
from coral.types import Attempt, Task

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SEC = 0.5

# Guards `increment_eval_count` (read-modify-write on .coral/public/eval_count).
# The daemon is the sole writer; this lock is only needed because pending
# attempts can be drained in parallel by multiple worker threads.
_eval_count_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Subprocess wrapper around the grader (keeps hard-kill semantics on timeout) #
# --------------------------------------------------------------------------- #

def _grader_worker(
    config_path: str,
    coral_dir: str,
    codebase_path: str,
    tasks: list,
    result_queue: Any,
) -> None:
    """Run grader.grade() in a child process. Puts result or exception into queue.

    We re-load the grader inside the child to avoid pickling issues with
    dynamically imported modules (grader.py loaded via importlib.util).
    """
    try:
        config = CoralConfig.from_yaml(config_path)
        grader = load_grader(config, coral_dir=coral_dir)
        result = asyncio.run(grader.grade(codebase_path, tasks))
        result_queue.put(("ok", result))
    except Exception as e:
        result_queue.put(("error", e, traceback.format_exc()))


def _run_grader_with_timeout(
    config_path: str,
    coral_dir: str,
    codebase_path: str,
    tasks: list,
    timeout: int,
) -> Any:
    """Run grader in a separate process with a hard timeout.

    multiprocessing + SIGKILL is the only reliable way to interrupt
    synchronous blocking code (numpy, Docker calls, etc.) on timeout.
    asyncio.wait_for can't.

    For entrypoint-based graders we skip the multiprocessing wrapper —
    SubprocessGrader already shells out to its own venv and applies the
    same timeout via subprocess.run, so doubling up would just add a
    no-op layer.
    """
    config = CoralConfig.from_yaml(config_path)
    if config.grader.entrypoint:
        grader = load_grader(config, coral_dir=coral_dir)
        return asyncio.run(grader.grade(codebase_path, tasks))

    if timeout <= 0:
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
            proc.kill()
            proc.join(timeout=5)
            raise TimeoutError(f"Grader timed out after {timeout}s")

        if result_queue.empty():
            raise RuntimeError("Grader process exited without returning a result")

        status, *payload = result_queue.get_nowait()
        if status == "ok":
            return payload[0]
        exc, tb_str = payload
        raise RuntimeError(f"Grader failed: {exc}\n{tb_str}")
    finally:
        result_queue.close()
        result_queue.join_thread()
        proc.close()


# --------------------------------------------------------------------------- #
# Isolated worktree management                                                #
# --------------------------------------------------------------------------- #

def _grader_checkouts_dir(coral_dir: Path) -> Path:
    d = coral_dir / "private" / "grader_checkouts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _repo_dir(coral_dir: Path) -> Path:
    """The per-run cloned repo. Production layout: run_dir/repo/. Test layout
    sometimes puts .coral/ directly inside the repo, so fall back to
    coral_dir.parent if that's also a git repo.
    """
    candidate = coral_dir.parent / "repo"
    if _is_git_repo(candidate):
        return candidate
    if _is_git_repo(coral_dir.parent):
        return coral_dir.parent
    raise RuntimeError(
        f"Cannot locate source repo from {coral_dir} "
        f"(tried {candidate} and {coral_dir.parent})"
    )


def _is_git_repo(path: Path) -> bool:
    """True if `path` exists and contains a .git directory/file."""
    return path.is_dir() and (path / ".git").exists()


def _add_isolated_worktree(repo_dir: Path, commit_hash: str, dest: Path) -> None:
    """Create a detached worktree at `dest` pointing at `commit_hash`.

    Force-removes any prior checkout at the same path (crash-recovery).
    """
    if dest.exists():
        _remove_worktree(repo_dir, dest)

    result = subprocess.run(
        ["git", "worktree", "add", "--detach", str(dest), commit_hash],
        capture_output=True, text=True, cwd=str(repo_dir),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git worktree add --detach {commit_hash[:12]} failed: {result.stderr.strip()}"
        )


def _remove_worktree(repo_dir: Path, dest: Path) -> None:
    """Remove a worktree. Best-effort; logs on failure but does not raise."""
    # git worktree remove is the preferred path; fall back to rmtree + prune.
    result = subprocess.run(
        ["git", "worktree", "remove", "--force", str(dest)],
        capture_output=True, text=True, cwd=str(repo_dir),
    )
    if result.returncode != 0:
        logger.warning(
            "git worktree remove %s failed (rc=%d): %s — falling back to rmtree",
            dest, result.returncode, result.stderr.strip(),
        )
        try:
            if dest.exists():
                shutil.rmtree(dest)
        except OSError as e:
            logger.warning("rmtree %s failed: %s", dest, e)
        subprocess.run(
            ["git", "worktree", "prune"],
            capture_output=True, text=True, cwd=str(repo_dir),
        )


# --------------------------------------------------------------------------- #
# Per-attempt grading                                                         #
# --------------------------------------------------------------------------- #

def _compute_status(
    score: float | None,
    agent_id: str,
    commit_hash: str,
    coral_dir: Path,
    minimize: bool,
) -> str:
    """Compare `score` to this agent's previous best to classify the attempt."""
    if score is None:
        return "crashed"

    prev_attempts = get_agent_attempts(str(coral_dir), agent_id)
    prev_scores = [
        a.score for a in prev_attempts
        if a.score is not None and a.commit_hash != commit_hash
    ]
    if not prev_scores:
        return "improved"

    prev_best = min(prev_scores) if minimize else max(prev_scores)
    if (minimize and score < prev_best) or (not minimize and score > prev_best):
        return "improved"
    if score == prev_best:
        return "baseline"
    return "regressed"


def _build_feedback(bundle: Any) -> str:
    """Combine bundle-level feedback + per-score explanations into one string."""
    parts = []
    if getattr(bundle, "feedback", None):
        parts.append(bundle.feedback)
    scores = getattr(bundle, "scores", None) or {}
    for name, s in scores.items():
        explanation = getattr(s, "explanation", None)
        if explanation:
            parts.append(f"{name}: {explanation}")
    return "\n".join(parts)


def _grade_one(
    attempt: Attempt,
    config_path: Path,
    coral_dir: Path,
    config: CoralConfig,
) -> Attempt:
    """Grade a single pending attempt and return the finalized Attempt record."""
    task = Task(
        id=config.task.name,
        name=config.task.name,
        description=config.task.description,
        metadata={},
    )
    timeout = config.grader.timeout
    minimize = config.grader.direction == "minimize"
    repo_dir = _repo_dir(coral_dir)
    checkout_path = _grader_checkouts_dir(coral_dir) / attempt.commit_hash

    score: float | None = None
    status = "crashed"
    feedback = ""
    metadata: dict = {}

    try:
        _add_isolated_worktree(repo_dir, attempt.commit_hash, checkout_path)
        try:
            bundle = _run_grader_with_timeout(
                str(config_path), str(coral_dir), str(checkout_path), [task], timeout,
            )
            score = bundle.aggregated
            feedback = _build_feedback(bundle)
            metadata = dict(getattr(bundle, "metadata", None) or {})
            status = _compute_status(
                score, attempt.agent_id, attempt.commit_hash, coral_dir, minimize,
            )
        finally:
            _remove_worktree(repo_dir, checkout_path)
    except TimeoutError:
        logger.error("Grader timed out on %s after %ss", attempt.commit_hash[:12], timeout)
        status = "timeout"
        feedback = f"Eval timed out after {timeout}s."
    except Exception as e:
        logger.exception("Grader crashed on %s", attempt.commit_hash[:12])
        status = "crashed"
        feedback = str(e)

    finalized = Attempt(
        commit_hash=attempt.commit_hash,
        agent_id=attempt.agent_id,
        title=attempt.title,
        score=score,
        status=status,
        parent_hash=attempt.parent_hash,
        # Preserve original submission timestamp; daemon doesn't re-stamp.
        timestamp=attempt.timestamp,
        feedback=feedback,
        shared_state_hash=attempt.shared_state_hash,
        parent_shared_state_hash=attempt.parent_shared_state_hash,
        metadata=metadata,
    )
    write_attempt(str(coral_dir), finalized)
    with _eval_count_lock:
        count = increment_eval_count(coral_dir)
    logger.info(
        "Graded #%d %s -> score=%s status=%s",
        count, attempt.commit_hash[:12],
        f"{score:.6f}" if score is not None else "None",
        status,
    )
    return finalized


# --------------------------------------------------------------------------- #
# Main loop                                                                   #
# --------------------------------------------------------------------------- #

def _find_pending(coral_dir: Path) -> list[Attempt]:
    """Return pending attempts in submission order (oldest first)."""
    attempts = read_attempts(coral_dir)
    pending = [a for a in attempts if a.status == "pending" and a.score is None]
    pending.sort(key=lambda a: a.timestamp)
    return pending


def _safe_grade_one(
    attempt: Attempt,
    config_path: Path,
    coral_dir: Path,
    config: CoralConfig,
) -> Attempt | None:
    """Grade an attempt, swallowing truly unexpected errors as `crashed`.

    Per-attempt failures (timeout, grader exception) are already turned into
    `crashed`/`timeout` Attempts inside `_grade_one`. This wrapper is the last
    line of defense so a thread in the pool can't take the daemon down.
    Returns the finalized Attempt, or None if even the crash-record write
    failed.
    """
    try:
        return _grade_one(attempt, config_path, coral_dir, config)
    except Exception:
        logger.exception(
            "Unhandled error grading %s; marking crashed", attempt.commit_hash[:12]
        )
        try:
            crashed = Attempt(
                commit_hash=attempt.commit_hash,
                agent_id=attempt.agent_id,
                title=attempt.title,
                score=None,
                status="crashed",
                parent_hash=attempt.parent_hash,
                timestamp=attempt.timestamp,
                feedback="Grader daemon hit an unexpected error; see logs.",
                shared_state_hash=attempt.shared_state_hash,
                parent_shared_state_hash=attempt.parent_shared_state_hash,
            )
            write_attempt(str(coral_dir), crashed)
            with _eval_count_lock:
                increment_eval_count(coral_dir)
            return crashed
        except Exception:
            logger.exception("Failed to record crash for %s", attempt.commit_hash[:12])
            return None


def _drain_pending(
    pending: list[Attempt],
    config_path: Path,
    coral_dir: Path,
    config: CoralConfig,
    *,
    max_workers: int,
    heartbeat_file: Path | None = None,
    should_stop: Callable[[], bool] = lambda: False,
) -> list[Attempt]:
    """Grade `pending` attempts via a worker pool of size `max_workers`.

    `max_workers=1` is serial — same behavior as the pre-pool daemon. Larger
    values let the daemon overlap grades when the operator has set
    `grader.parallel.max_workers` higher (only safe for concurrency-safe
    graders).

    Stop semantics: when `should_stop()` becomes true, queued (not-yet-running)
    futures are cancelled. Already-running grades finish — same as the old
    serial loop, where a stop signal mid-attempt waited for that attempt.
    """
    finalized: list[Attempt] = []
    if not pending:
        return finalized

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_safe_grade_one, attempt, config_path, coral_dir, config): attempt
            for attempt in pending
        }
        try:
            for fut in as_completed(futures):
                if heartbeat_file is not None:
                    try:
                        heartbeat_file.write_text(datetime.now(UTC).isoformat())
                    except OSError:
                        pass
                result = fut.result()
                if result is not None:
                    finalized.append(result)
                if should_stop():
                    for queued in futures:
                        queued.cancel()
                    break
        finally:
            # ThreadPoolExecutor.__exit__ waits for in-flight grades (their
            # subprocesses already own the work and will return on their own
            # timeout). We don't kill mid-grade workers from a stop signal.
            pass
    return finalized


def process_pending_once(coral_dir: str | Path) -> list[Attempt]:
    """Drain all currently-pending attempts synchronously and return finalized records.

    Intended for tests and one-shot grading workflows where spawning a
    separate daemon process is overkill. Shares code with the main loop.
    """
    coral_dir = Path(coral_dir).resolve()
    config_path = coral_dir / "config.yaml"
    config = CoralConfig.from_yaml(config_path)
    return _drain_pending(
        _find_pending(coral_dir),
        config_path,
        coral_dir,
        config,
        max_workers=config.grader.parallel.max_workers,
    )


def run_daemon(coral_dir: str | Path, stop_event: Any = None) -> None:
    """Watch coral_dir/public/attempts/ and grade pending entries.

    Loops until `stop_event.is_set()` (multiprocessing.Event) or SIGTERM.
    Grader instance itself is (re)loaded once per iteration by
    `_run_grader_with_timeout` in a child process — the expensive bit (Docker
    init, dataset parsing, etc.) can amortize across evals if the grader
    exposes module-level caches.
    """
    coral_dir = Path(coral_dir).resolve()
    config_path = coral_dir / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"No config.yaml at {config_path}")

    config = CoralConfig.from_yaml(config_path)
    max_workers = config.grader.parallel.max_workers

    logger.info(
        "Grader daemon started (coral_dir=%s, max_workers=%d)",
        coral_dir, max_workers,
    )
    started_at = datetime.now(UTC).isoformat()
    heartbeat_file = coral_dir / "public" / "grader_daemon_heartbeat"
    heartbeat_file.write_text(started_at)

    def _should_stop() -> bool:
        return bool(stop_event and stop_event.is_set())

    while not _should_stop():
        try:
            pending = _find_pending(coral_dir)
        except Exception:
            logger.exception("Failed to scan for pending attempts")
            pending = []

        if not pending:
            # Idle heartbeat so supervisors can tell the daemon is alive.
            try:
                heartbeat_file.write_text(datetime.now(UTC).isoformat())
            except OSError:
                pass
            time.sleep(_POLL_INTERVAL_SEC)
            continue

        _drain_pending(
            pending,
            config_path,
            coral_dir,
            config,
            max_workers=max_workers,
            heartbeat_file=heartbeat_file,
            should_stop=_should_stop,
        )

    logger.info("Grader daemon stopped")
