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
import json
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
    write_attempt,
)
from coral.types import (
    BUDGET_CLASS_GRADER_ERROR,
    Attempt,
    Task,
    get_budget_class,
)

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SEC = 0.5

# Headroom on top of `grader.timeout` before the daemon SIGKILLs the worker.
# Inner timers (asyncio.wait_for in TaskGrader, subprocess.run(timeout=...) in
# per-grader code) all use the user-configured `grader.timeout`. Without
# headroom they race the daemon's outer hard-kill — a kernel that just barely
# overruns can land as either status="failure"/budget_class="real" (inner
# timer wins, returns a clean self.fail bundle) or status="timeout"/
# budget_class="grader_error" (outer wins). Same wall-clock condition, two
# different leaderboard accountings.
#
# Giving the outer timer a grace window means the inner timer is the
# *intended* one to fire; the daemon hard-kill is the safety net for graders
# that hang past it (e.g. C extensions or sleeps that ignore cancellation).
_TIMEOUT_GRACE_SECONDS = 30

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
    island_id: str | int | None = None,
) -> None:
    """Run grader.grade() in a child process. Puts result or exception into queue.

    We re-load the grader inside the child to avoid pickling issues with
    dynamically imported modules (grader.py loaded via importlib.util).
    """
    try:
        config = CoralConfig.from_yaml(config_path)
        grader = load_grader(config, coral_dir=coral_dir)
        grade_kwargs: dict[str, Any] = {}
        if island_id is not None:
            grade_kwargs["island_id"] = island_id
        result = asyncio.run(grader.grade(codebase_path, tasks, **grade_kwargs))
        result_queue.put(("ok", result))
    except Exception as e:
        result_queue.put(("error", e, traceback.format_exc()))


def _run_grader_with_timeout(
    config_path: str,
    coral_dir: str,
    codebase_path: str,
    tasks: list,
    timeout: int,
    island_id: str | int | None = None,
) -> Any:
    """Run grader in a separate process with a hard timeout.

    multiprocessing + SIGKILL is the only reliable way to interrupt
    synchronous blocking code (numpy, Docker calls, etc.) on timeout.
    asyncio.wait_for can't.

    The hard-kill fires at ``timeout + _TIMEOUT_GRACE_SECONDS``, not at
    ``timeout`` exactly. The user-configured ``timeout`` is also threaded
    through inner timers (TaskGrader.grade's asyncio.wait_for, per-grader
    subprocess.run(timeout=...)). Without headroom the outer hard-kill races
    them — see the comment on _TIMEOUT_GRACE_SECONDS for why. Inner timers
    should fire first and return a clean self.fail bundle; the daemon kill
    is the safety net.

    For entrypoint-based graders we skip the multiprocessing wrapper —
    SubprocessGrader already shells out to its own venv and applies the
    same timeout via subprocess.run, so doubling up would just add a
    no-op layer.

    ``island_id`` is forwarded so the grader can scope hub reads
    (e.g. ``read_attempts(coral_dir, island_id=...)``) to the attempt's
    own island in multi-island runs. ``None`` in single-island mode and
    when the attempt was submitted without an island context — the inner
    grader's ``self.island_id`` defaults to None in that case.
    """
    config = CoralConfig.from_yaml(config_path)
    grade_kwargs: dict[str, Any] = {}
    if island_id is not None:
        grade_kwargs["island_id"] = island_id
    if config.grader.entrypoint:
        grader = load_grader(config, coral_dir=coral_dir)
        return asyncio.run(grader.grade(codebase_path, tasks, **grade_kwargs))

    if timeout <= 0:
        grader = load_grader(config, coral_dir=coral_dir)
        return asyncio.run(grader.grade(codebase_path, tasks, **grade_kwargs))

    hard_kill_deadline = timeout + _TIMEOUT_GRACE_SECONDS
    result_queue: multiprocessing.Queue = multiprocessing.Queue()
    proc = multiprocessing.Process(
        target=_grader_worker,
        args=(config_path, coral_dir, codebase_path, tasks, result_queue, island_id),
    )
    try:
        proc.start()
        proc.join(timeout=hard_kill_deadline)

        if proc.is_alive():
            proc.kill()
            proc.join(timeout=5)
            raise TimeoutError(
                f"Grader exceeded {timeout}s + {_TIMEOUT_GRACE_SECONDS}s grace and was killed"
            )

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
        f"Cannot locate source repo from {coral_dir} (tried {candidate} and {coral_dir.parent})"
    )


def _is_git_repo(path: Path) -> bool:
    """True if `path` exists and contains a .git directory/file."""
    return path.is_dir() and (path / ".git").exists()


_WORKTREE_ADD_RETRIES = 3
_WORKTREE_ADD_RETRY_BACKOFF = 0.05  # seconds; the worktree TOCTOU window is <100ms
# Match the exact race-condition message git emits when two ``git worktree add``
# invocations collide on the same repo. Strings come from git's own
# builtin/worktree.c; matching verbatim keeps the retry scoped to the race
# rather than masking real failures.
_WORKTREE_RACE_MARKERS = (
    "failed to read .git/worktrees/",
    "cannot lock ref",  # extra coverage for the same TOCTOU on refs
)


def _is_worktree_race(stderr: str) -> bool:
    return any(marker in stderr for marker in _WORKTREE_RACE_MARKERS)


def _add_isolated_worktree(repo_dir: Path, commit_hash: str, dest: Path) -> None:
    """Create a detached worktree at `dest` pointing at `commit_hash`.

    Force-removes any prior checkout at the same path (crash-recovery).
    Retries on git's known ``worktree add`` TOCTOU race ("failed to read
    .git/worktrees/<id>/commondir") — two parallel invocations from the
    same repo can race even when the calls are independent. Retries with a
    small backoff; preserves ``grader.parallel.max_workers > 1`` overlap.
    """
    if dest.exists():
        _remove_worktree(repo_dir, dest)

    last_err = ""
    for attempt in range(_WORKTREE_ADD_RETRIES):
        result = subprocess.run(
            ["git", "worktree", "add", "--detach", str(dest), commit_hash],
            capture_output=True,
            text=True,
            cwd=str(repo_dir),
        )
        if result.returncode == 0:
            return
        last_err = result.stderr.strip()
        if not _is_worktree_race(last_err) or attempt == _WORKTREE_ADD_RETRIES - 1:
            break
        time.sleep(_WORKTREE_ADD_RETRY_BACKOFF)
    raise RuntimeError(f"git worktree add --detach {commit_hash[:12]} failed: {last_err}")


def _remove_worktree(repo_dir: Path, dest: Path) -> None:
    """Remove a worktree. Best-effort; logs on failure but does not raise."""
    # git worktree remove is the preferred path; fall back to rmtree + prune.
    result = subprocess.run(
        ["git", "worktree", "remove", "--force", str(dest)],
        capture_output=True,
        text=True,
        cwd=str(repo_dir),
    )
    if result.returncode != 0:
        logger.warning(
            "git worktree remove %s failed (rc=%d): %s — falling back to rmtree",
            dest,
            result.returncode,
            result.stderr.strip(),
        )
        try:
            if dest.exists():
                shutil.rmtree(dest)
        except OSError as e:
            logger.warning("rmtree %s failed: %s", dest, e)
        subprocess.run(
            ["git", "worktree", "prune"],
            capture_output=True,
            text=True,
            cwd=str(repo_dir),
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
    island_id: str | None = None,
) -> str:
    """Compare `score` to this agent's previous best to classify the attempt."""
    if score is None:
        return "crashed"

    prev_attempts = get_agent_attempts(str(coral_dir), agent_id, island_id=island_id)
    prev_scores = [
        a.score for a in prev_attempts if a.score is not None and a.commit_hash != commit_hash
    ]
    if not prev_scores:
        return "improved"

    prev_best = min(prev_scores) if minimize else max(prev_scores)
    if (minimize and score < prev_best) or (not minimize and score > prev_best):
        return "improved"
    if score == prev_best:
        return "baseline"
    return "regressed"


def _attempt_island_id(attempt: Attempt) -> str | None:
    island_id = (attempt.metadata or {}).get("island_id")
    if island_id is None:
        return None
    return str(island_id)


def _read_attempt_file(path: Path) -> Attempt | None:
    try:
        return Attempt.from_dict(json.loads(path.read_text()))
    except (json.JSONDecodeError, KeyError, OSError, TypeError):
        return None


def _current_attempt_location(
    coral_dir: Path,
    commit_hash: str,
    *,
    fallback_island_id: str | int | None,
) -> tuple[Attempt | None, str | None]:
    """Find where an attempt record currently lives.

    Migration can move a pending attempt while a grader worker is already
    running on its commit. Finalization must write to the moved record's
    current island, not the island captured when the worker was queued.
    """
    fallback = str(fallback_island_id) if fallback_island_id is not None else None
    islands_dir = coral_dir / "islands"
    if not islands_dir.exists():
        attempt_path = coral_dir / "public" / "attempts" / f"{commit_hash}.json"
        return _read_attempt_file(attempt_path), None

    matches: list[tuple[Attempt, str, float]] = []
    for island_dir in sorted(p for p in islands_dir.iterdir() if p.is_dir()):
        path = island_dir / "attempts" / f"{commit_hash}.json"
        if not path.exists():
            continue
        attempt = _read_attempt_file(path)
        if attempt is None:
            logger.warning(
                "Skipping malformed attempt record while locating %s: %s",
                commit_hash,
                path,
            )
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        matches.append((attempt, island_dir.name, mtime))

    if not matches:
        return None, fallback
    if len(matches) > 1:
        logger.warning(
            "Attempt %s exists in multiple islands; using the current-looking record",
            commit_hash[:12],
        )
    current_matches = [
        (attempt, island_id, mtime)
        for attempt, island_id, mtime in matches
        if _attempt_island_id(attempt) == island_id
    ]
    if current_matches:
        attempt, island_id, _mtime = max(current_matches, key=lambda item: item[2])
        return attempt, island_id
    attempt, island_id, _mtime = max(matches, key=lambda item: item[2])
    return attempt, island_id


def _move_eval_logs_to_current_island(
    coral_dir: Path,
    commit_hash: str,
    *,
    from_island_id: str | int | None,
    to_island_id: str | int | None,
) -> None:
    """Move eval logs written through a stale island context to the final island."""
    if from_island_id is None or to_island_id is None:
        return
    src_island = str(from_island_id)
    dst_island = str(to_island_id)
    if src_island == dst_island:
        return

    src = coral_dir / "islands" / src_island / "eval_logs" / commit_hash
    if not src.exists():
        return
    dst = coral_dir / "islands" / dst_island / "eval_logs" / commit_hash
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
            shutil.rmtree(src, ignore_errors=True)
        else:
            if dst.exists():
                if dst.is_dir():
                    shutil.rmtree(dst)
                else:
                    dst.unlink()
            shutil.move(str(src), str(dst))
    except OSError as e:
        logger.warning(
            "Failed to move eval logs for %s from island %s to %s: %s",
            commit_hash[:12],
            src_island,
            dst_island,
            e,
        )


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


# Fallback shared-dir names per runtime. Used by _append_eval_logs_hint when
# the runtime isn't registered in coral.agent.registry (e.g. custom entrypoint
# runtimes). Mirrors the .shared_dir_name contract in coral/agent/runtime.py.
_DEFAULT_SHARED_DIR_BY_RUNTIME: dict[str, str] = {
    "claude_code": ".claude",
    "codex": ".codex",
    "opencode": ".opencode",
    "cursor_agent": ".cursor",
    "kiro": ".kiro",
}


def _resolve_shared_dir(runtime_name: str) -> str:
    """Look up a runtime's shared-dir name; fall back to .claude.

    The shared dir is the worktree-local directory the agent reads state
    from — `.claude/`, `.codex/`, etc. The eval_logs symlink in
    setup_shared_state targets that dir, so the agent accesses their
    attempt's logs at `<shared_dir>/eval_logs/<hash>/`.
    """
    if not runtime_name:
        return ".claude"
    try:
        from coral.agent.registry import get_runtime

        return get_runtime(runtime_name).shared_dir_name
    except (KeyError, ImportError, Exception):  # noqa: BLE001 — best-effort hint
        return _DEFAULT_SHARED_DIR_BY_RUNTIME.get(runtime_name, ".claude")


def _append_eval_logs_hint(
    feedback: str,
    commit_hash: str,
    runtime_name: str,
) -> str:
    """Append a footer pointing the agent at their per-attempt trace logs.

    Universal across success / timeout / crashed feedback paths. The grader's
    own _parse_job_result also includes a Logs block with per-trial paths;
    this footer is the safety net for the cases where the grader never
    reached _parse_job_result (timeout mid-run, harbor never produced a
    result.json, exception in the worker subprocess, etc.).

    The path is given in BOTH worktree-relative form (always correct) and
    concrete-with-shared-dir form (correct for this run's runtime). The
    agent prepends their own shared-dir to read.
    """
    shared_dir = _resolve_shared_dir(runtime_name)
    rel_path = f"eval_logs/{commit_hash}/"
    footer = (
        f"\n\n### Trace logs\n"
        f"Per-attempt harbor logs (agent trajectories, terminal recordings, "
        f"verifier output): `{rel_path}` — in your worktree that resolves to "
        f"`{shared_dir}/{rel_path}` (your runtime's shared state dir; "
        f"`.codex/`, `.opencode/`, `.kiro/` on other runtimes)."
    )
    return (feedback or "") + footer


def _grade_one(
    attempt: Attempt,
    config_path: Path,
    coral_dir: Path,
    config: CoralConfig,
) -> Attempt:
    """Grade a single pending attempt and return the finalized Attempt record."""
    grading_island_id = _attempt_island_id(attempt)
    # Task.metadata is the canonical channel for surfacing per-attempt context
    # to the user's grader (read via TaskGrader.tune / .budget_class). Both
    # the in-process and SubprocessGrader paths serialize it, so this works
    # for either runtime. Final budget_class may flip to "grader_error" below.
    budget_class = get_budget_class(attempt.metadata)
    task = Task(
        id=config.task.name,
        name=config.task.name,
        description=config.task.description,
        metadata={
            "budget_class": budget_class,
            "agent_id": attempt.agent_id,
            "commit_hash": attempt.commit_hash,
        },
    )
    timeout = config.grader.timeout
    minimize = config.grader.direction == "minimize"
    repo_dir = _repo_dir(coral_dir)
    checkout_path = _grader_checkouts_dir(coral_dir) / attempt.commit_hash

    score: float | None = None
    status = "crashed"
    feedback = ""
    metadata: dict = {}
    grader_completed = False

    try:
        _add_isolated_worktree(repo_dir, attempt.commit_hash, checkout_path)
        try:
            bundle = _run_grader_with_timeout(
                str(config_path),
                str(coral_dir),
                str(checkout_path),
                [task],
                timeout,
                island_id=grading_island_id,
            )
            score = bundle.aggregated
            feedback = _build_feedback(bundle)
            metadata = dict(getattr(bundle, "metadata", None) or {})
            grader_completed = True
        finally:
            _remove_worktree(repo_dir, checkout_path)
    except TimeoutError:
        logger.error("Grader timed out on %s after %ss", attempt.commit_hash[:12], timeout)
        status = "timeout"
        feedback = f"Eval timed out after {timeout}s."
        budget_class = BUDGET_CLASS_GRADER_ERROR
    except Exception as e:
        logger.exception("Grader crashed on %s", attempt.commit_hash[:12])
        status = "crashed"
        feedback = str(e)
        budget_class = BUDGET_CLASS_GRADER_ERROR

    current_attempt, final_island_id = _current_attempt_location(
        coral_dir,
        attempt.commit_hash,
        fallback_island_id=grading_island_id,
    )
    base_attempt = current_attempt or attempt
    _move_eval_logs_to_current_island(
        coral_dir,
        attempt.commit_hash,
        from_island_id=grading_island_id,
        to_island_id=final_island_id,
    )

    if grader_completed:
        status = _compute_status(
            score,
            base_attempt.agent_id,
            base_attempt.commit_hash,
            coral_dir,
            minimize,
            island_id=final_island_id,
        )

    # Append the per-attempt eval_logs path so the agent can always find
    # their trace logs, regardless of which feedback path produced this
    # result (success / timeout / crashed). This is the universal safety
    # net — see _append_eval_logs_hint for the contract.
    feedback = _append_eval_logs_hint(feedback, attempt.commit_hash, config.agents.runtime)

    # Carry forward any pending metadata the grader bundle didn't overwrite,
    # then stamp the final budget_class (always wins over any pending value).
    for k, v in (base_attempt.metadata or {}).items():
        metadata.setdefault(k, v)
    if final_island_id is not None:
        metadata["island_id"] = final_island_id
    metadata["budget_class"] = budget_class

    finalized = Attempt(
        commit_hash=base_attempt.commit_hash,
        agent_id=base_attempt.agent_id,
        title=base_attempt.title,
        score=score,
        status=status,
        parent_hash=base_attempt.parent_hash,
        # Preserve original submission timestamp; daemon doesn't re-stamp.
        timestamp=base_attempt.timestamp,
        feedback=feedback,
        shared_state_hash=base_attempt.shared_state_hash,
        parent_shared_state_hash=base_attempt.parent_shared_state_hash,
        metadata=metadata,
    )
    write_attempt(str(coral_dir), finalized, island_id=final_island_id)
    with _eval_count_lock:
        count = increment_eval_count(coral_dir, island_id=final_island_id)
    logger.info(
        "Graded #%d %s -> score=%s status=%s",
        count,
        attempt.commit_hash[:12],
        f"{score:.6f}" if score is not None else "None",
        status,
    )
    return finalized


# --------------------------------------------------------------------------- #
# Main loop                                                                   #
# --------------------------------------------------------------------------- #


def _find_pending(coral_dir: Path) -> list[Attempt]:
    """Return pending attempts (across all islands in multi-island mode), oldest first."""
    if (coral_dir / "islands").exists():
        islands = sorted((coral_dir / "islands").iterdir())
        attempt_dirs = [d / "attempts" for d in islands if d.is_dir()]
    else:
        attempt_dirs = [coral_dir / "public" / "attempts"]

    pending: list[Attempt] = []
    for d in attempt_dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.json")):
            try:
                data = json.loads(p.read_text())
                a = Attempt.from_dict(data)
            except Exception:
                continue
            if a.status == "pending" and a.score is None:
                pending.append(a)
    pending.sort(key=lambda x: x.timestamp)
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
        logger.exception("Unhandled error grading %s; marking crashed", attempt.commit_hash[:12])
        try:
            grading_island_id = _attempt_island_id(attempt)
            current_attempt, final_island_id = _current_attempt_location(
                coral_dir,
                attempt.commit_hash,
                fallback_island_id=grading_island_id,
            )
            base_attempt = current_attempt or attempt
            _move_eval_logs_to_current_island(
                coral_dir,
                attempt.commit_hash,
                from_island_id=grading_island_id,
                to_island_id=final_island_id,
            )
            metadata = dict(base_attempt.metadata or {})
            if final_island_id is not None:
                metadata["island_id"] = final_island_id
            metadata["budget_class"] = BUDGET_CLASS_GRADER_ERROR
            crashed = Attempt(
                commit_hash=base_attempt.commit_hash,
                agent_id=base_attempt.agent_id,
                title=base_attempt.title,
                score=None,
                status="crashed",
                parent_hash=base_attempt.parent_hash,
                timestamp=base_attempt.timestamp,
                feedback="Grader daemon hit an unexpected error; see logs.",
                shared_state_hash=base_attempt.shared_state_hash,
                parent_shared_state_hash=base_attempt.parent_shared_state_hash,
                metadata=metadata,
            )
            write_attempt(str(coral_dir), crashed, island_id=final_island_id)
            with _eval_count_lock:
                increment_eval_count(coral_dir, island_id=final_island_id)
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
        coral_dir,
        max_workers,
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
