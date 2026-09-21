"""Evolving-criteria wrapper around ``AgenticEvaluator``.

The evolution machinery itself is CORAL core (``coral.grader.evolution``); this
module only names the inner grader. ``AgenticEvaluator`` supplies the two
optional hooks (log path, failure classification) directly.

``grader.entrypoint: agentic_evaluator.evolution:EvolvingAgenticEvaluator``
"""

from __future__ import annotations

from agentic_evaluator.grader import AgenticEvaluator
from coral.grader.evolution import EvolvingTaskGrader


class EvolvingAgenticEvaluator(EvolvingTaskGrader):
    inner_grader_cls = AgenticEvaluator
