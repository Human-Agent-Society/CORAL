"""Function-based grader that wraps user-defined functions."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any

from coral.types import Score, ScoreBundle, Task
from coral.grader.base import BaseGrader

GraderFunc = Callable[[str, list[Task]], Score | float | bool]
AsyncGraderFunc = Callable[[str, list[Task]], Any]


class FunctionGrader(BaseGrader):
    """Grader that wraps a user-defined function.

    The function should accept (codebase_path, tasks) and return:
    - Score: Full score object
    - float/int: Numeric score (0.0 to 1.0 recommended)
    - bool: Pass/fail (True = 1.0, False = 0.0)
    """

    def __init__(
        self,
        name: str,
        func: GraderFunc | AsyncGraderFunc,
        description: str = "",
        is_public: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(name, description, is_public, **kwargs)
        self.func = func
        self._is_async = inspect.iscoroutinefunction(func)

    async def grade(
        self,
        codebase_path: str,
        tasks: list[Task],
        **kwargs: Any,
    ) -> ScoreBundle:
        if self._is_async:
            result = await self.func(codebase_path, tasks)
        else:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self.func, codebase_path, tasks)

        score = self._normalize_result(result)
        return self._make_bundle(score, aggregated=score.to_float())

    def _normalize_result(self, result: Score | float | int | bool) -> Score:
        if isinstance(result, Score):
            return result
        elif isinstance(result, bool):
            return self._make_score(
                value=1.0 if result else 0.0,
                explanation="Pass" if result else "Fail",
            )
        elif isinstance(result, float | int):
            return self._make_score(value=float(result))
        else:
            raise ValueError(
                f"FunctionGrader {self.name}: unexpected return type {type(result)}. "
                "Expected Score, float, int, or bool."
            )

    @classmethod
    def wrap(
        cls,
        name: str,
        description: str = "",
        is_public: bool = True,
        **kwargs: Any,
    ) -> Callable[[GraderFunc], FunctionGrader]:
        def decorator(func: GraderFunc) -> FunctionGrader:
            return cls(
                name=name,
                func=func,
                description=description or func.__doc__ or "",
                is_public=is_public,
                **kwargs,
            )
        return decorator


def function_grader(
    name: str,
    is_public: bool = True,
    **kwargs: Any,
) -> Callable[[GraderFunc], FunctionGrader]:
    """Decorator to create a FunctionGrader."""
    return FunctionGrader.wrap(name=name, is_public=is_public, **kwargs)
