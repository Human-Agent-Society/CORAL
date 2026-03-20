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
    """Single evaluation score."""

    value: float | str | bool | None
    name: str
    explanation: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_float(self) -> float | None:
        if self.value is None:
            return None
        if isinstance(self.value, bool):
            return 1.0 if self.value else 0.0
        elif isinstance(self.value, int | float):
            return float(self.value)
        elif isinstance(self.value, str):
            mapping = {
                "CORRECT": 1.0, "C": 1.0,
                "INCORRECT": 0.0, "I": 0.0,
                "PARTIAL": 0.5, "P": 0.5,
                "NOANSWER": 0.0, "N": 0.0,
            }
            return mapping.get(self.value.upper(), 0.0)
        return 0.0

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

    def get(self, name: str) -> Score | None:
        return self.scores.get(name)

    def get_score_value(self, name: str, default: float = 0.0) -> float:
        score = self.scores.get(name)
        if score is None:
            return default
        return score.to_float()

    def compute_aggregated(self, weights: dict[str, float] | None = None) -> float:
        weights = weights or {}
        total = 0.0
        weight_sum = 0.0
        for name, score in self.scores.items():
            try:
                value = score.to_float()
                weight = weights.get(name, 1.0)
                total += value * weight
                weight_sum += weight
            except (ValueError, TypeError):
                continue
        return total / weight_sum if weight_sum > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "scores": {name: score.to_dict() for name, score in self.scores.items()},
            "aggregated": self.aggregated,
            "is_public": self.is_public,
        }
        if self.feedback is not None:
            d["feedback"] = self.feedback
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScoreBundle:
        scores = {name: Score.from_dict(s) for name, s in data.get("scores", {}).items()}
        return cls(
            scores=scores,
            aggregated=data.get("aggregated"),
            is_public=data.get("is_public", True),
            feedback=data.get("feedback"),
        )


@dataclass
class Attempt:
    """Record of a single optimization attempt by an agent."""

    commit_hash: str
    agent_id: str
    title: str
    score: float | None
    status: str  # "improved" | "baseline" | "regressed" | "reverted" | "crashed" | "timeout"
    parent_hash: str | None
    timestamp: str
    feedback: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "commit_hash": self.commit_hash,
            "agent_id": self.agent_id,
            "title": self.title,
            "score": self.score,
            "status": self.status,
            "parent_hash": self.parent_hash,
            "timestamp": self.timestamp,
            "feedback": self.feedback,
        }

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
        )
