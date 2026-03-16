"""Grader system for CORAL."""

from coral.grader.base import BaseGrader
from coral.grader.builtin.function_grader import FunctionGrader, function_grader
from coral.grader.protocol import GraderInterface
from coral.grader.task_grader import TaskGrader

__all__ = [
    "BaseGrader",
    "FunctionGrader",
    "GraderInterface",
    "TaskGrader",
    "function_grader",
]
