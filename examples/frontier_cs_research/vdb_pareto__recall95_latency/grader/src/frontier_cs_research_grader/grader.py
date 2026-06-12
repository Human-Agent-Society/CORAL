"""Frontier-CS Research grader — uses frontier_cs package.

Delegates evaluation to the frontier_cs SingleEvaluator which handles
Docker-based execution and scoring.
"""

from __future__ import annotations

from pathlib import Path

from coral.grader import TaskGrader
from coral.types import ScoreBundle


class Grader(TaskGrader):
    """Grader for a Frontier-CS research problem via frontier_cs package."""

    def evaluate(self) -> ScoreBundle:
        problem_name = self.args.get("problem_name", "")
        variant_name = self.args.get("variant_name", "")
        language = self.args.get("language", "python")

        if not problem_name:
            return self.fail("grader arg 'problem_name' is required")

        # Build problem_id for frontier_cs API
        if variant_name:
            problem_id = f"{problem_name}/{variant_name}"
        else:
            problem_id = problem_name

        # Find solution
        sol_file = "solution.cpp" if language == "cpp" else "solution.py"
        solution_path = Path(self.codebase_path) / sol_file
        if not solution_path.exists():
            return self.score(0.0, feedback=f"No {sol_file} found in workspace.")

        code = solution_path.read_text()
        if not code.strip():
            return self.score(0.0, feedback=f"{sol_file} is empty.")

        # Use frontier_cs evaluator
        from frontier_cs import SingleEvaluator

        evaluator = SingleEvaluator(backend="docker", register_cleanup=False)
        result = evaluator.evaluate("research", problem_id=problem_id, code=code)

        if not result.success:
            msg = result.message or "Evaluation failed"
            return self.score(0.0, feedback=msg)

        score = result.score if result.score is not None else 0.0

        feedback_parts = [f"Score: {score:.2f}/100"]
        if result.metadata:
            for key in ["score_unbounded", "accuracy", "speedup", "avg_runtime"]:
                val = result.metadata.get(key)
                if val is not None:
                    feedback_parts.append(f"{key}: {val}")

        return self.score(score, feedback="\n".join(feedback_parts))
