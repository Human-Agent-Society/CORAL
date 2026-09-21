"""Structured evaluation-failure codes.

A single "N% crash rate" hides causes with different fixes: turn-budget
terminations are configuration, account session limits are scheduling, and a
rate-limited evaluator can exit with subtype ``success`` after writing nothing.

``classify_generic`` knows only about signals every ``claude -p``-driven
evaluator shares. Task-specific graders refine it through the optional
``classify_failure`` hook (see ``grader.py``), keeping this module free of any
one evaluator's message strings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class FailureCode(StrEnum):
    MAX_TURNS = "max_turns"
    ACCOUNT_SESSION_LIMIT = "account_session_limit"
    PLAYWRIGHT_UNAVAILABLE = "playwright_unavailable"
    INVALID_OUTPUT = "invalid_output"
    TIMEOUT = "timeout"
    SUBPROCESS_FAILURE = "subprocess_failure"
    UNKNOWN = "unknown"


@dataclass
class FailureRecord:
    code: FailureCode
    attempt_number: int
    explanation: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "attempt_number": self.attempt_number,
            "explanation": self.explanation[:500],
            "evidence": self.evidence,
        }


def inspect_evaluator_log(log_path: Path | None) -> dict[str, Any]:
    """Terminal ``result`` event and session-limit marker from a ``claude -p``
    stream-json transcript. Empty dict if there is no log."""
    info: dict[str, Any] = {}
    if not log_path or not Path(log_path).exists():
        return info
    try:
        for line in Path(log_path).read_text(errors="replace").splitlines():
            if "hit your session limit" in line:
                info["session_limit_marker"] = True
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") == "result":
                for k in ("subtype", "num_turns", "duration_ms", "total_cost_usd", "is_error"):
                    info[k if k != "subtype" else "terminal_subtype"] = d.get(k)
    except OSError:
        pass
    return info


def classify_generic(explanation: str, log_info: dict[str, Any] | None = None) -> FailureCode:
    """Signals common to any CLI-driven evaluator. Session limit is checked
    first because it can co-occur with a ``success`` terminal subtype."""
    log_info = log_info or {}
    text = (explanation or "").casefold()
    if log_info.get("session_limit_marker") or "session limit" in text or "rate limit" in text:
        return FailureCode.ACCOUNT_SESSION_LIMIT
    if log_info.get("terminal_subtype") == "error_max_turns":
        return FailureCode.MAX_TURNS
    if "timed out" in text or "did not complete within" in text or "timeout" in text:
        return FailureCode.TIMEOUT
    if "could not launch" in text or "exited " in text:
        return FailureCode.SUBPROCESS_FAILURE
    return FailureCode.UNKNOWN


def summarize(records: list[FailureRecord]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in records:
        out[r.code.value] = out.get(r.code.value, 0) + 1
    return out
