"""Grader protocol — the only interface contract in CORAL."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from coral.types import ScoreBundle, Task


@runtime_checkable
class GraderInterface(Protocol):
    """Evaluate a codebase on tasks and return scores."""

    async def grade(
        self,
        codebase_path: str,
        tasks: list[Task],
        **kwargs: Any,
    ) -> ScoreBundle: ...
