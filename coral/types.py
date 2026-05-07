"""Core type definitions for CORAL.

Simplified from the old codebase — only types needed for the agent hub pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Task:
    """A unit of work for agents to optimize."""

    id: str
    name: str
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            description=data["description"],
            metadata=data.get("metadata", {}),
        )


@dataclass
class Score:
    """Single evaluation score.

    `value` is a number (or None when the grader couldn't produce a result —
    e.g. a timeout). Pass/fail and verdict-style outputs must be converted to
    a float by the grader before constructing the Score; the framework does
    not infer a number from a string label, since the mapping it would have
    to use ("PASS"? "CORRECT"? "1"?) is task-specific.
    """

    value: float | int | None
    name: str
    explanation: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "name": self.name,
            "explanation": self.explanation,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Score:
        return cls(
            value=data["value"],
            name=data["name"],
            explanation=data.get("explanation"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ScoreBundle:
    """Collection of scores from evaluation."""

    scores: dict[str, Score]
    aggregated: float | None = None
    is_public: bool = True
    feedback: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def get(self, name: str) -> Score | None:
        return self.scores.get(name)

    def get_score_value(self, name: str, default: float = 0.0) -> float:
        score = self.scores.get(name)
        if score is None or score.value is None:
            return default
        return float(score.value)

    def compute_aggregated(self, weights: dict[str, float] | None = None) -> float:
        weights = weights or {}
        total = 0.0
        weight_sum = 0.0
        for name, score in self.scores.items():
            if score.value is None:
                continue
            weight = weights.get(name, 1.0)
            total += float(score.value) * weight
            weight_sum += weight
        return total / weight_sum if weight_sum > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "scores": {name: score.to_dict() for name, score in self.scores.items()},
            "aggregated": self.aggregated,
            "is_public": self.is_public,
        }
        if self.feedback is not None:
            d["feedback"] = self.feedback
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScoreBundle:
        scores = {name: Score.from_dict(s) for name, s in data.get("scores", {}).items()}
        return cls(
            scores=scores,
            aggregated=data.get("aggregated"),
            is_public=data.get("is_public", True),
            feedback=data.get("feedback"),
            metadata=data.get("metadata", {}),
        )


# Budget classification for an attempt. Stored on `Attempt.metadata["budget_class"]`.
#
# - "real":         a genuine optimization attempt — counts toward plateau / heartbeat triggers.
# - "grader_error": grader timeout or grader-side exception — the eval machinery itself broke,
#                   not a real fail of the agent's code.
# - "tune":         agent-submitted in tune mode — config/hyperparam exploration.
#
# Attempts without this metadata key are treated as "real" (backward compat).
BUDGET_CLASS_REAL = "real"
BUDGET_CLASS_GRADER_ERROR = "grader_error"
BUDGET_CLASS_TUNE = "tune"
_VALID_BUDGET_CLASSES = (BUDGET_CLASS_REAL, BUDGET_CLASS_GRADER_ERROR, BUDGET_CLASS_TUNE)


def get_budget_class(metadata: dict[str, Any] | None) -> str:
    """Read the budget class from attempt metadata, defaulting to 'real'."""
    if not metadata:
        return BUDGET_CLASS_REAL
    cls = metadata.get("budget_class")
    if cls in _VALID_BUDGET_CLASSES:
        return cls
    return BUDGET_CLASS_REAL


@dataclass
class Attempt:
    """Record of a single optimization attempt by an agent."""

    commit_hash: str
    agent_id: str
    title: str
    score: float | None
    status: str  # "pending" | "improved" | "baseline" | "regressed" | "reverted" | "crashed" | "timeout"
    parent_hash: str | None
    timestamp: str
    feedback: str = ""
    shared_state_hash: str | None = None
    parent_shared_state_hash: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def budget_class(self) -> str:
        """Budget classification: 'real', 'grader_error', or 'tune'. Defaults to 'real'."""
        return get_budget_class(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "commit_hash": self.commit_hash,
            "agent_id": self.agent_id,
            "title": self.title,
            "score": self.score,
            "status": self.status,
            "parent_hash": self.parent_hash,
            "timestamp": self.timestamp,
            "feedback": self.feedback,
        }
        if self.shared_state_hash is not None:
            d["shared_state_hash"] = self.shared_state_hash
        if self.parent_shared_state_hash is not None:
            d["parent_shared_state_hash"] = self.parent_shared_state_hash
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Attempt:
        return cls(
            commit_hash=data["commit_hash"],
            agent_id=data["agent_id"],
            title=data["title"],
            score=data.get("score"),
            status=data.get("status", "crashed"),
            parent_hash=data.get("parent_hash"),
            timestamp=data["timestamp"],
            feedback=data.get("feedback", ""),
            shared_state_hash=data.get("shared_state_hash"),
            parent_shared_state_hash=data.get("parent_shared_state_hash"),
            metadata=data.get("metadata", {}),
        )
