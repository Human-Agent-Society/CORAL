"""Shared helpers for classifying an agent subprocess exit.

The crash-burst circuit breaker only counts "no_result" / "session_error" exits.
A clean exit (e.g. `max_turns` reached and the agent emitted a final result, or
the process ran for a healthy duration before exiting 0) must not increment the
burst counter — otherwise legitimate completions trip the breaker.

`classify_by_uptime` is the conservative default for runtimes that do not emit
a stable terminal marker. `claude_code_has_result` recognizes the stream-json
shape that Claude Code uses; other runtimes fall back to the uptime heuristic.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Literal

ExitClassification = Literal["clean", "no_result", "session_error"]


def classify_by_uptime(
    exit_code: int | None, uptime_seconds: float | None, min_clean_runtime_seconds: int
) -> ExitClassification:
    """Classify an exit using only exit code and observed uptime.

    Returns "clean" only when exit_code is 0 and the process ran long enough
    that we believe it produced real work; otherwise "no_result". This is the
    safe default for runtimes (codex / opencode / kiro) that lack a terminal
    marker in their log format.
    """
    if (
        exit_code == 0
        and uptime_seconds is not None
        and uptime_seconds >= min_clean_runtime_seconds
    ):
        return "clean"
    return "no_result"


def claude_code_has_result(log_path: Path) -> bool:
    """Return True iff the agent emitted a 'type:result' line in its stream-json log.

    Claude Code writes a final `{"type":"result", ...}` line on normal session
    completion (including `max_turns` reached). Reading the file's tail is
    sufficient — the result is the last meaningful line. We tolerate both
    `"type":"result"` and `"type": "result"` spacing.
    """
    if not log_path.exists():
        return False
    try:
        # Tail the file — result line is near the end. 64 lines is plenty.
        tail: deque[str] = deque(maxlen=64)
        with open(log_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                tail.append(line)
        for line in reversed(tail):
            if '"type":"result"' in line or '"type": "result"' in line:
                return True
    except OSError:
        return False
    return False
