"""CRUD for .coral/public/attempts/*.json + leaderboard formatting."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from coral.types import Attempt


def _attempts_dir(coral_dir: str | Path) -> Path:
    d = Path(coral_dir) / "public" / "attempts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_attempt(coral_dir: str | Path, attempt: Attempt) -> Path:
    """Write an attempt record to JSON atomically (tmp + rename).

    Readers (monitor loop, grader daemon, `coral wait`) may poll these files
    concurrently with writes. Using tmp + rename guarantees readers see either
    the old complete file or the new complete file, never a partial write.
    """
    path = _attempts_dir(coral_dir) / f"{attempt.commit_hash}.json"
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


def read_attempt(coral_dir: str | Path, commit_hash: str) -> Attempt | None:
    """Read a single attempt by commit hash. Returns None if missing or malformed."""
    path = _attempts_dir(coral_dir) / f"{commit_hash}.json"
    if not path.exists():
        return None
    try:
        return Attempt.from_dict(json.loads(path.read_text()))
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def increment_eval_count(coral_dir: str | Path) -> int:
    """Increment the global eval counter at .coral/public/eval_count and return the new value."""
    counter_file = Path(coral_dir) / "public" / "eval_count"
    count = 0
    if counter_file.exists():
        try:
            count = int(counter_file.read_text().strip())
        except ValueError:
            pass
    count += 1
    counter_file.write_text(str(count))
    return count


def read_eval_count(coral_dir: str | Path) -> int:
    """Read the global eval counter (0 if missing)."""
    counter_file = Path(coral_dir) / "public" / "eval_count"
    if not counter_file.exists():
        return 0
    try:
        return int(counter_file.read_text().strip())
    except ValueError:
        return 0


def read_attempts(coral_dir: str | Path) -> list[Attempt]:
    """Read all attempt records."""
    d = _attempts_dir(coral_dir)
    attempts = []
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            attempts.append(Attempt.from_dict(data))
        except (json.JSONDecodeError, KeyError):
            continue
    return attempts


def get_leaderboard(coral_dir: str | Path, top_n: int = 20, direction: str = "maximize") -> list[Attempt]:
    """Get top N attempts sorted by score. Direction controls sort order."""
    attempts = read_attempts(coral_dir)
    scored = [a for a in attempts if a.score is not None]
    descending = direction != "minimize"
    scored.sort(key=lambda a: a.score or 0.0, reverse=descending)
    return scored[:top_n]


def get_agent_attempts(coral_dir: str | Path, agent_id: str) -> list[Attempt]:
    """Get all attempts from a specific agent."""
    return [a for a in read_attempts(coral_dir) if a.agent_id == agent_id]


def get_recent(coral_dir: str | Path, n: int = 10) -> list[Attempt]:
    """Get N most recent attempts (by timestamp)."""
    attempts = read_attempts(coral_dir)
    attempts.sort(key=lambda a: a.timestamp, reverse=True)
    return attempts[:n]


def search_attempts(coral_dir: str | Path, query: str) -> list[Attempt]:
    """Full-text search over attempt titles, feedback, and status."""
    query_lower = query.lower()
    results = []
    for attempt in read_attempts(coral_dir):
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
        "| Rank | Score            | Agent   | Title                                    | Time        | Commit   |",
        "|------|------------------|---------|------------------------------------------|-------------|----------|",
    ]
    for i, a in enumerate(attempts, 1):
        score_str = f"{a.score:.10f}" if a.score is not None else "—"
        commit_short = a.commit_hash[:8]
        title = a.title[:40].ljust(40) if a.title else "—".ljust(40)
        time_str = _format_time(a.timestamp)
        lines.append(
            f"| {i:<4} | {score_str:>16} | {a.agent_id:<7} | {title} | {time_str:<11} | {commit_short} |"
        )

    return "\n".join(lines)


def format_status_summary(coral_dir: str | Path, direction: str = "maximize") -> str:
    """Format a summary of the current run state."""
    attempts = read_attempts(coral_dir)
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
        lines.append(
            f"Worst: {worst.score:.10f}  ({worst.title[:50]})"
        )

    if scored:
        first_time = min(a.timestamp for a in attempts)
        last_time = max(a.timestamp for a in attempts)
        lines.append(f"First attempt: {_format_time(first_time)}  |  Latest: {_format_time(last_time)}")

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
