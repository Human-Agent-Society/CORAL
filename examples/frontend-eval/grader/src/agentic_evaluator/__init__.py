"""Agentic evaluator graders for CORAL.

- ``AgenticEvaluator`` — fixed criteria; a fresh evaluator agent per attempt
  scores live output through Playwright.
- ``EvolvingAgenticEvaluator`` — the same, wrapped by CORAL core's
  ``coral.grader.evolution.EvolvingTaskGrader``.
- ``agentic_evaluator.evolving`` — the v1 evolving grader, retained only so the
  2026-08-30 pilot data stays interpretable. Deprecated.
"""

from agentic_evaluator.evolution import EvolvingAgenticEvaluator
from agentic_evaluator.grader import AgenticEvaluator

__all__ = ["AgenticEvaluator", "EvolvingAgenticEvaluator"]
