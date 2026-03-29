"""Request and result data structures for the eval queue."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EvalRequest:
    """An eval request written by the agent, read by the dispatcher."""

    ticket_id: str  # UUID
    agent_id: str
    commit_hash: str
    config_path: str  # path to config.yaml
    coral_dir: str  # path to .coral/
    codebase_path: str  # agent's worktree path
    timestamp: str  # ISO8601
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "agent_id": self.agent_id,
            "commit_hash": self.commit_hash,
            "config_path": self.config_path,
            "coral_dir": self.coral_dir,
            "codebase_path": self.codebase_path,
            "timestamp": self.timestamp,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalRequest:
        return cls(
            ticket_id=data["ticket_id"],
            agent_id=data["agent_id"],
            commit_hash=data["commit_hash"],
            config_path=data["config_path"],
            coral_dir=data["coral_dir"],
            codebase_path=data["codebase_path"],
            timestamp=data["timestamp"],
            priority=data.get("priority", 0),
        )

    def to_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def from_json(cls, path: Path) -> EvalRequest:
        return cls.from_dict(json.loads(path.read_text()))


@dataclass
class EvalResult:
    """A grading result written by the dispatcher, read by the agent."""

    ticket_id: str
    score: float | None
    scores: dict[str, Any] = field(default_factory=dict)  # serialized ScoreBundle.scores
    feedback: str = ""
    status: str = "ok"  # "ok" | "timeout" | "error"
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "score": self.score,
            "scores": self.scores,
            "feedback": self.feedback,
            "status": self.status,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalResult:
        return cls(
            ticket_id=data["ticket_id"],
            score=data.get("score"),
            scores=data.get("scores", {}),
            feedback=data.get("feedback", ""),
            status=data.get("status", "ok"),
            error=data.get("error", ""),
        )

    def to_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def from_json(cls, path: Path) -> EvalResult:
        return cls.from_dict(json.loads(path.read_text()))
