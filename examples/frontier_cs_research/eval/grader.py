"""Frontier-CS Research batch grader.

Evaluates all Python solutions found in solutions/ against the Frontier-CS
research evaluation framework. Returns the average score across all attempted
problems.
"""

from __future__ import annotations

import sys
from pathlib import Path

from coral.grader import TaskGrader
from coral.types import Score, ScoreBundle


class Grader(TaskGrader):
    """Batch grader for Frontier-CS research problems.

    Scans solutions/ for solution.py files (possibly nested by variant),
    evaluates each via SingleEvaluator, and returns the average score.
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

        evaluator = SingleEvaluator(
            backend=backend,
            base_dir=frontier_cs_path,
            register_cleanup=False,
        )

        # Count total problems from the Frontier-CS repo (each evaluator.py = one problem)
        research_problems_dir = frontier_cs_path / "research" / "problems"
        total_problems = sum(1 for _ in research_problems_dir.rglob("evaluator.py"))

        solutions_dir = Path(self.codebase_path) / "solutions"
        solution_entries = _discover_solutions(solutions_dir) if solutions_dir.exists() else []

        if not solution_entries:
            return self.score(0.0, feedback=f"No solutions found (0/{total_problems} problems)")

        scores: dict[str, Score] = {}
        total_score = 0.0
        attempted = 0
        lines: list[str] = []

        for problem_id, sol_path in sorted(solution_entries):
            code = sol_path.read_text(encoding="utf-8")
            score_key = problem_id.replace("/", "_")

            try:
                result = evaluator.evaluate("research", problem_id, code)
            except Exception as e:
                scores[score_key] = Score(
                    value=0.0, name=score_key,
                )
                lines.append(f"{problem_id}: 0.00 (error: {e})")
                attempted += 1
                continue

            problem_score = result.score if result.score is not None else 0.0
            if result.status != EvaluationStatus.SUCCESS:
                problem_score = 0.0

            scores[score_key] = Score(
                value=problem_score, name=score_key,
            )
            total_score += problem_score
            attempted += 1

            status_str = "ok" if result.success else result.status.value
            lines.append(f"{problem_id}: {problem_score:.2f} ({status_str})")

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


def _discover_solutions(solutions_dir: Path) -> list[tuple[str, Path]]:
    """Find all solution.py files and map them to Frontier-CS problem IDs.

    Returns list of (problem_id, solution_path) tuples.
    E.g.:
      solutions/flash_attn/solution.py       -> ("flash_attn", Path(...))
      solutions/gemm_optimization/squares/solution.py
                                              -> ("gemm_optimization/squares", Path(...))
    """
    entries = []
    for sol_file in solutions_dir.rglob("solution.py"):
        rel = sol_file.parent.relative_to(solutions_dir)
        problem_id = str(rel)
        if problem_id == ".":
            continue
        entries.append((problem_id, sol_file))
    return entries
