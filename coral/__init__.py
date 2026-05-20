"""CORAL - Orchestration system for autonomous coding agents."""

from importlib.metadata import version

__version__ = version("coral")

from coral.config import CoralConfig
from coral.types import Attempt, Score, ScoreBundle, Task

__all__ = [
    "Attempt",
    "CoralConfig",
    "Score",
    "ScoreBundle",
    "Task",
]
