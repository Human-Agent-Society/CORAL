"""Frontier-CS Algorithmic grader — uses frontier_cs package.

Delegates evaluation to the frontier_cs SingleEvaluator which handles
compilation, sandboxed execution, and scoring via the go-judge Docker server.
"""

from __future__ import annotations

from pathlib import Path

from coral.grader import TaskGrader
from coral.types import ScoreBundle


class Grader(TaskGrader):
    """Grader for a Frontier-CS algorithmic problem via frontier_cs package."""

    def evaluate(self) -> ScoreBundle:
        problem_id = self.args.get("problem_id")
        if not problem_id:
            return self.fail("grader arg 'problem_id' is required")

        # Find solution
        solution_path = Path(self.codebase_path) / "solution.cpp"
        if not solution_path.exists():
            return self.score(0.0, feedback="No solution.cpp found in workspace.")

        code = solution_path.read_text()
        if not code.strip():
            return self.score(0.0, feedback="solution.cpp is empty.")

        # Use frontier_cs evaluator
        from frontier_cs import SingleEvaluator

        evaluator = SingleEvaluator(register_cleanup=False)
        result = evaluator.evaluate(
            "algorithmic", problem_id=problem_id, code=code,
        )

        if not result.success:
            msg = result.message or "Evaluation failed"
            return self.score(0.0, feedback=msg)

        score = result.score if result.score is not None else 0.0
        return self.score(score, feedback=f"Score: {score:.2f}/100")
