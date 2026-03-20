"""Frontier-CS Algorithmic batch grader.

Evaluates all C++ solutions found in solutions/ against the Frontier-CS
go-judge server. Returns the average score across all attempted problems.
"""

from __future__ import annotations

import sys
from pathlib import Path

from coral.grader import TaskGrader
from coral.types import Score, ScoreBundle


class Grader(TaskGrader):
    """Batch grader for Frontier-CS algorithmic problems.

    Scans solutions/ for .cpp files, evaluates each via SingleEvaluator,
    and returns the average score. Problems without solutions are skipped.
    """

    def evaluate(self) -> ScoreBundle:
        frontier_cs_dir = self.args.get("frontier_cs_dir")
        if not frontier_cs_dir:
            return self.fail("grader arg 'frontier_cs_dir' is required")

        frontier_cs_path = Path(frontier_cs_dir)
        if not frontier_cs_path.exists():
            return self.fail(f"Frontier-CS directory not found: {frontier_cs_dir}")

        # Add Frontier-CS src to path so we can import the evaluator
        src_path = str(frontier_cs_path / "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)

        from frontier_cs.single_evaluator import SingleEvaluator
        from frontier_cs.runner.base import EvaluationStatus

        backend = self.args.get("backend", "docker")
        judge_url = self.args.get("judge_url", "http://localhost:8081")

        evaluator = SingleEvaluator(
            backend=backend,
            base_dir=frontier_cs_path,
            judge_url=judge_url,
            register_cleanup=False,
        )

        # Count total problems from the Frontier-CS repo
        problems_dir = frontier_cs_path / "algorithmic" / "problems"
        all_problem_ids = sorted(
            [d.name for d in problems_dir.iterdir() if d.is_dir() and not d.name.startswith(".")],
            key=lambda x: (int(x) if x.isdigit() else float("inf"), x),
        )
        total_problems = len(all_problem_ids)

        solutions_dir = Path(self.codebase_path) / "solutions"
        if not solutions_dir.exists() or not list(solutions_dir.glob("*.cpp")):
            return self.score(0.0, feedback=f"No solutions found (0/{total_problems} problems)")

        scores: dict[str, Score] = {}
        total_score = 0.0
        attempted = 0
        lines: list[str] = []

        for sol_file in sorted(solutions_dir.glob("*.cpp")):
            problem_id = sol_file.stem
            code = sol_file.read_text(encoding="utf-8")

            try:
                result = evaluator.evaluate("algorithmic", problem_id, code)
            except Exception as e:
                scores[f"problem_{problem_id}"] = Score(
                    value=0.0, name=f"problem_{problem_id}",
                )
                lines.append(f"problem {problem_id}: 0.00 (error: {e})")
                attempted += 1
                continue

            problem_score = result.score if result.score is not None else 0.0
            if result.status != EvaluationStatus.SUCCESS:
                problem_score = 0.0

            scores[f"problem_{problem_id}"] = Score(
                value=problem_score, name=f"problem_{problem_id}",
            )
            total_score += problem_score
            attempted += 1

            status_str = "ok" if result.success else result.status.value
            lines.append(f"problem {problem_id}: {problem_score:.2f} ({status_str})")

        # Average over ALL problems, not just attempted ones
        avg_score = total_score / total_problems

        feedback = (
            f"Solved {attempted}/{total_problems} problems | Average: {avg_score:.4f}\n"
            + "\n".join(lines)
        )

        return ScoreBundle(
            scores=scores,
            aggregated=avg_score,
            feedback=feedback,
        )
