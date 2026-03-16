"""Base grader class for CORAL."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from coral.types import Score, ScoreBundle, Task


class BaseGrader(ABC):
    """Abstract base class for graders.

    Graders evaluate a codebase (agent workspace) on a set of tasks.
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        is_public: bool = True,
        **kwargs: Any,
    ) -> None:
        self.name = name
        self.description = description
        self.is_public = is_public
        self.config = kwargs

    @abstractmethod
    async def grade(
        self,
        codebase_path: str,
        tasks: list[Task],
        **kwargs: Any,
    ) -> ScoreBundle:
        """Evaluate codebase on tasks. Must be implemented by subclasses."""
        ...

    def grade_sync(
        self,
        codebase_path: str,
        tasks: list[Task],
        **kwargs: Any,
    ) -> ScoreBundle:
        """Synchronous wrapper for grade()."""
        return asyncio.run(self.grade(codebase_path, tasks, **kwargs))

    def _make_score(
        self,
        value: float | str | bool,
        explanation: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Score:
        """Helper to create a Score with this grader's name."""
        return Score(
            value=value,
            name=self.name,
            explanation=explanation,
            metadata=metadata or {},
        )

    def _make_bundle(
        self,
        score: Score,
        aggregated: float | None = None,
    ) -> ScoreBundle:
        """Helper to create a ScoreBundle with this grader's settings."""
        return ScoreBundle(
            scores={self.name: score},
            aggregated=aggregated,
            is_public=self.is_public,
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
