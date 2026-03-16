"""CORAL - Orchestration system for autonomous coding agents."""

__version__ = "0.2.0"

from coral.types import Attempt, Score, ScoreBundle, Task
from coral.config import CoralConfig

__all__ = [
    "Attempt",
    "CoralConfig",
    "Score",
    "ScoreBundle",
    "Task",
]
