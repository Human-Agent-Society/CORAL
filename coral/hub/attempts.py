"""CRUD for .coral/public/attempts/*.json + leaderboard formatting."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from coral.hub._island import island_root
from coral.types import Attempt


def _attempts_dir(coral_dir: str | Path, island_id: str | int | None = None) -> Path:
    d = island_root(coral_dir, island_id) / "attempts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_attempt(
    coral_dir: str | Path,
    attempt: Attempt,
    island_id: str | int | None = None,
) -> Path:
    """Write an attempt record to JSON atomically (tmp + rename).

    Readers (monitor loop, grader daemon, `coral wait`) may poll these files
    concurrently with writes. Using tmp + rename guarantees readers see either
    the old complete file or the new complete file, never a partial write.
    """
    path = _attempts_dir(coral_dir, island_id) / f"{attempt.commit_hash}.json"
    payload = json.dumps(attempt.to_dict(), indent=2)
    # Write to a temp file in the same directory (same filesystem -> atomic rename).
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{attempt.commit_hash}.",
        suffix=".json.tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file on any failure so we don't leak .tmp files.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return path


def read_attempt(
    coral_dir: str | Path,
    commit_hash: str,
    island_id: str | int | None = None,
) -> Attempt | None:
    """Read a single attempt by commit hash. Returns None if missing or malformed."""
    path = _attempts_dir(coral_dir, island_id) / f"{commit_hash}.json"
    if not path.exists():
        return None
    try:
        return Attempt.from_dict(json.loads(path.read_text()))
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def set_user_best(coral_dir: str | Path, commit_hash: str) -> Attempt | None:
    """Mark one attempt as the user-selected best and clear prior marks."""
    from coral.hub._island import all_view_roots

    target: Attempt | None = None
    for view_root in all_view_roots(coral_dir):
        attempts_dir = view_root / "attempts"
        if not attempts_dir.is_dir():
            continue
        for path in sorted(attempts_dir.glob("*.json")):
            try:
                attempt = Attempt.from_dict(json.loads(path.read_text()))
            except (json.JSONDecodeError, KeyError, OSError):
                continue
            is_target = attempt.commit_hash == commit_hash
            if is_target:
                attempt.metadata["user_best"] = True
                target = attempt
            elif attempt.metadata.get("user_best") is True:
                attempt.metadata.pop("user_best", None)
            else:
                continue
            payload = json.dumps(attempt.to_dict(), indent=2)
            fd, tmp_path = tempfile.mkstemp(
                prefix=f".{attempt.commit_hash}.",
                suffix=".json.tmp",
                dir=path.parent,
            )
            try:
                with os.fdopen(fd, "w") as f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
    return target


def _global_eval_count_path(coral_dir: str | Path) -> Path:
    """Global counter: coral_dir/eval_count in multi-island, public/eval_count in single."""
    coral_dir = Path(coral_dir)
    if (coral_dir / "islands").exists():
        return coral_dir / "eval_count"
    return coral_dir / "public" / "eval_count"


def increment_eval_count(coral_dir: str | Path, island_id: str | int | None = None) -> int:
    """Increment the eval counter(s) and return the new per-scope value.

    When ``island_id`` is provided, increments BOTH the per-island counter
    (at ``islands/<id>/eval_count``) and the global counter (at
    ``coral_dir/eval_count`` in multi-island, ``public/eval_count`` in
    single). Returns the per-island value.

    When ``island_id`` is None, increments only the global counter and
    returns its new value.
    """

    def _bump(p: Path) -> int:
        count = 0
        if p.exists():
            try:
                count = int(p.read_text().strip())
            except ValueError:
                pass
        count += 1
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(count))
        return count

    global_path = _global_eval_count_path(coral_dir)
    global_count = _bump(global_path)
    if island_id is None:
        return global_count
    return _bump(island_root(coral_dir, island_id) / "eval_count")


def read_eval_count(coral_dir: str | Path, island_id: str | int | None = None) -> int:
    """Read the eval counter (0 if missing).

    With ``island_id=None``, returns the global counter (today's path in
    single-island mode, ``coral_dir/eval_count`` in multi-island).
    With ``island_id`` set, returns the per-island counter at
    ``islands/<id>/eval_count``.
    """
    if island_id is None:
        path = _global_eval_count_path(coral_dir)
    else:
        path = island_root(coral_dir, island_id) / "eval_count"
    if not path.exists():
        return 0
    try:
        return int(path.read_text().strip())
    except ValueError:
        return 0


def read_attempts(coral_dir: str | Path, island_id: str | int | None = None) -> list[Attempt]:
    """Read all attempt records."""
    d = _attempts_dir(coral_dir, island_id)
    attempts = []
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            attempts.append(Attempt.from_dict(data))
        except (json.JSONDecodeError, KeyError):
            continue
    return attempts


def _read_all_island_attempts(coral_dir: str | Path) -> list[Attempt]:
    """Read attempts across all islands. Used by views that span the whole run.

    In single-island mode (no `islands/` on disk) reads from `public/attempts/`.
    In multi-island mode reads from every `islands/<id>/attempts/` and
    concatenates. Centralised so every "show me the whole team" view (status
    summary, leaderboard, agent breakdown) doesn't need its own copy of the
    detection logic.
    """
    coral_dir = Path(coral_dir)
    if (coral_dir / "islands").exists():
        attempts: list[Attempt] = []
        for island_root in sorted((coral_dir / "islands").iterdir()):
            if not island_root.is_dir():
                continue
            attempts.extend(read_attempts(coral_dir, island_id=island_root.name))
        return attempts
    return read_attempts(coral_dir, island_id=None)


def get_leaderboard(
    coral_dir: str | Path,
    top_n: int = 20,
    direction: str = "maximize",
    island_id: str | int | None = None,
    *,
    include_tune: bool = False,
) -> list[Attempt]:
    """Get top N attempts sorted by score. Direction controls sort order.

    With ``island_id=None`` in a multi-island run, reads across all islands
    so the leaderboard reflects the whole team. Tune attempts are hidden
    by default — they are sweeps, not submissions; pass ``include_tune=True``
    (or use ``coral log --all``) to see them.
    """
    coral_dir = Path(coral_dir)
    if island_id is not None or not (coral_dir / "islands").exists():
        attempts = read_attempts(coral_dir, island_id=island_id)
    else:
        attempts = _read_all_island_attempts(coral_dir)
    scored = [a for a in attempts if a.score is not None]
    if not include_tune:
        from coral.types import BUDGET_CLASS_REAL  # local import: avoid cycle at module load

        scored = [a for a in scored if a.budget_class == BUDGET_CLASS_REAL]
    descending = direction != "minimize"
    scored.sort(key=lambda a: a.score or 0.0, reverse=descending)
    return scored[:top_n]


def get_agent_attempts(
    coral_dir: str | Path,
    agent_id: str,
    island_id: str | int | None = None,
) -> list[Attempt]:
    """Get all attempts from a specific agent.

    When ``island_id`` is None in multi-island mode, scans every island.
    Partition-prefixed agent ids (``0-agent-1``) encode the agent's birth
    island, not necessarily its current island after migration, so the prefix
    must not be used for current-location routing.
    """
    coral_dir = Path(coral_dir)
    if island_id is None and (coral_dir / "islands").exists():
        attempts: list[Attempt] = []
        for view_root in _all_view_attempt_roots(coral_dir):
            attempts.extend(
                a
                for a in read_attempts(coral_dir, island_id=view_root.name)
                if a.agent_id == agent_id
            )
        return attempts
    return [a for a in read_attempts(coral_dir, island_id=island_id) if a.agent_id == agent_id]


def _all_view_attempt_roots(coral_dir: Path) -> list[Path]:
    """Per-island attempt dirs in multi-island mode (sorted)."""
    from coral.hub._island import all_view_roots

    return [r for r in all_view_roots(coral_dir) if r.name.isdigit()]


def agent_in_grader_queue(
    coral_dir: str | Path,
    agent_id: str,
    attempts: list[Attempt] | None = None,
    island_id: str | int | None = None,
) -> Attempt | None:
    """Return the agent's newest pending attempt if any is in the grader queue.

    A pending attempt is one with `status == "pending"` and `score is None` —
    matching the daemon's own `_find_pending` filter. When multiple pending
    attempts exist for the same agent (e.g. the agent crashed and resubmitted
    while a prior attempt was still queued), the newest by ISO timestamp is
    returned so the stall-watchdog exemption uses the most relevant evidence.
    Callers (e.g. the manager monitor loop) should pass a pre-fetched
    `attempts` list once per tick to avoid rescanning the JSON directory for
    every agent.
    """
    if attempts is None:
        attempts = read_attempts(coral_dir, island_id=island_id)
    candidates = [
        a for a in attempts if a.agent_id == agent_id and a.status == "pending" and a.score is None
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda a: a.timestamp, reverse=True)
    return candidates[0]


def count_agent_pending(
    coral_dir: str | Path,
    agent_id: str,
    attempts: list[Attempt] | None = None,
    island_id: str | int | None = None,
) -> int:
    """Return the number of pending attempts owned by `agent_id`.

    Uses the same filter as `agent_in_grader_queue` (status=="pending" and
    score is None). Pass a pre-fetched `attempts` list to avoid a duplicate
    directory scan when the caller already has one.
    """
    if attempts is None:
        attempts = read_attempts(coral_dir, island_id=island_id)
    return sum(
        1 for a in attempts if a.agent_id == agent_id and a.status == "pending" and a.score is None
    )


def get_recent(
    coral_dir: str | Path,
    n: int = 10,
    island_id: str | int | None = None,
) -> list[Attempt]:
    """Get N most recent attempts (by timestamp).

    With ``island_id=None`` in multi-island mode, scans every island so the
    result reflects the whole team's recent activity.
    """
    coral_dir = Path(coral_dir)
    if island_id is not None or not (coral_dir / "islands").exists():
        attempts = read_attempts(coral_dir, island_id=island_id)
    else:
        attempts = _read_all_island_attempts(coral_dir)
    attempts.sort(key=lambda a: a.timestamp, reverse=True)
    return attempts[:n]


def per_agent_class_counts(
    coral_dir: str | Path, island_id: str | int | None = None
) -> dict[str, dict[str, int]]:
    """Tally finalized attempts per agent, split by budget_class.

    Returns ``{agent_id: {"real": n, "grader_error": n, "tune": n}}``.
    Pending attempts (not yet graded) are skipped; they don't have a final
    classification. Used by `coral status` to surface per-agent grader-error rate.
    """
    counts: dict[str, dict[str, int]] = {}
    for a in read_attempts(coral_dir, island_id=island_id):
        if a.status == "pending":
            continue
        bucket = counts.setdefault(a.agent_id, {})
        bucket[a.budget_class] = bucket.get(a.budget_class, 0) + 1
    return counts


def search_attempts(
    coral_dir: str | Path,
    query: str,
    island_id: str | int | None = None,
) -> list[Attempt]:
    """Full-text search over attempt titles, feedback, and status.

    With ``island_id=None`` in multi-island mode, searches every island.
    """
    coral_dir = Path(coral_dir)
    if island_id is not None or not (coral_dir / "islands").exists():
        sources = read_attempts(coral_dir, island_id=island_id)
    else:
        sources = _read_all_island_attempts(coral_dir)
    query_lower = query.lower()
    results = []
    for attempt in sources:
        text = f"{attempt.title} {attempt.feedback} {attempt.status}".lower()
        if query_lower in text:
            results.append(attempt)
    return results


def _format_time(timestamp: str) -> str:
    """Format ISO timestamp to short human-readable form."""
    try:
        dt = datetime.fromisoformat(timestamp)
        return dt.strftime("%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return timestamp[:19] if timestamp else "—"


def format_leaderboard(attempts: list[Attempt]) -> str:
    """Format attempts as a markdown leaderboard table."""
    if not attempts:
        return "No attempts yet."

    lines = [
        "| Rank | Score            | Agent   | Class  | Title                                    | Time        | Commit   |",
        "|------|------------------|---------|--------|------------------------------------------|-------------|----------|",
    ]
    for i, a in enumerate(attempts, 1):
        score_str = f"{a.score:.10f}" if a.score is not None else "—"
        commit_short = a.commit_hash[:8]
        title = a.title[:40].ljust(40) if a.title else "—".ljust(40)
        time_str = _format_time(a.timestamp)
        # Display "error" instead of full "grader_error" to keep the column narrow.
        class_str = "error" if a.budget_class == "grader_error" else a.budget_class
        lines.append(
            f"| {i:<4} | {score_str:>16} | {a.agent_id:<7} | {class_str:<6} | {title} | {time_str:<11} | {commit_short} |"
        )

    return "\n".join(lines)


def format_status_summary(
    coral_dir: str | Path,
    direction: str = "maximize",
    island_id: str | int | None = None,
    *,
    include_tune: bool = False,
) -> str:
    """Format a summary of the current run state.

    In single-island mode, reads from ``coral_dir/public/attempts/`` (the
    legacy layout). In multi-island mode with a specific ``island_id``,
    reads from that island's attempts. In multi-island mode without an
    ``island_id``, aggregates across every island so ``coral status`` shows
    the whole team in one view. Tune attempts are hidden from the
    headline numbers by default (Best/Worst and per-agent best) — pass
    ``include_tune=True`` to count them.
    """
    coral_dir = Path(coral_dir)
    if island_id is not None:
        attempts = read_attempts(coral_dir, island_id=island_id)
    else:
        attempts = _read_all_island_attempts(coral_dir)

    if not include_tune:
        from coral.types import BUDGET_CLASS_REAL

        attempts = [a for a in attempts if a.budget_class == BUDGET_CLASS_REAL]

    if not attempts:
        return "No attempts yet."

    total = len(attempts)
    scored = [a for a in attempts if a.score is not None]
    crashed = [a for a in attempts if a.status == "crashed"]

    if direction == "minimize":
        best = min(scored, key=lambda a: a.score or 0.0) if scored else None
        worst = max(scored, key=lambda a: a.score or 0.0) if scored else None
    else:
        best = max(scored, key=lambda a: a.score or 0.0) if scored else None
        worst = min(scored, key=lambda a: a.score or 0.0) if scored else None

    # Per-agent stats
    agents: dict[str, list[Attempt]] = {}
    for a in attempts:
        agents.setdefault(a.agent_id, []).append(a)

    lines = [
        f"Total attempts: {total}  |  Scored: {len(scored)}  |  Crashed: {len(crashed)}",
    ]

    if best:
        lines.append(
            f"Best:  {best.score:.10f}  ({best.title[:50]})  @ {_format_time(best.timestamp)}"
        )
    if worst and best and worst.commit_hash != best.commit_hash:
        lines.append(f"Worst: {worst.score:.10f}  ({worst.title[:50]})")

    if scored:
        first_time = min(a.timestamp for a in attempts)
        last_time = max(a.timestamp for a in attempts)
        lines.append(
            f"First attempt: {_format_time(first_time)}  |  Latest: {_format_time(last_time)}"
        )

    # Per-agent breakdown
    lines.append("")
    lines.append("Per-agent:")
    for aid in sorted(agents.keys()):
        agent_attempts = agents[aid]
        agent_scored = [a for a in agent_attempts if a.score is not None]
        if agent_scored:
            if direction == "minimize":
                agent_best = min(agent_scored, key=lambda a: a.score or 0.0)
            else:
                agent_best = max(agent_scored, key=lambda a: a.score or 0.0)
        else:
            agent_best = None
        best_str = f"best={agent_best.score:.10f}" if agent_best else "no scored attempts"
        lines.append(f"  {aid}: {len(agent_attempts)} attempts, {best_str}")

    return "\n".join(lines)
