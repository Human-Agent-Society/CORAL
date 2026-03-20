"""Frontier-CS Research batch grader.

Evaluates all Python solutions found in solutions/ by running Docker-based
evaluation. Returns the average score across all attempted problems.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from coral.grader import TaskGrader
from coral.types import Score, ScoreBundle

DEFAULT_TIMEOUT = 600


class Grader(TaskGrader):
    """Batch grader for Frontier-CS research problems.

    Scans solutions/ for solution.py files (possibly nested by variant),
    evaluates each via Docker, and returns the average score.
    """

    def evaluate(self) -> ScoreBundle:
        problems_dir = self.args.get("problems_dir")
        if not problems_dir:
            return self.fail("grader arg 'problems_dir' is required")

        problems_path = Path(problems_dir)
        if not problems_path.exists():
            return self.fail(f"Problems directory not found: {problems_dir}")

        # Count total problems (each evaluator.py = one problem)
        total_problems = sum(1 for _ in problems_path.rglob("evaluator.py"))

        solutions_dir = Path(self.codebase_path) / "solutions"
        solution_entries = _discover_solutions(solutions_dir) if solutions_dir.exists() else []

        if not solution_entries:
            return self.score(0.0, feedback=f"No solutions found (0/{total_problems} problems)")

        scores: dict[str, Score] = {}
        total_score = 0.0
        attempted = 0

        for problem_id, sol_path in sorted(solution_entries):
            score_key = problem_id.replace("/", "_")
            problem_dir = problems_path / problem_id

            if not problem_dir.exists():
                scores[score_key] = Score(value=0.0, name=score_key, explanation="problem dir not found")
                attempted += 1
                continue

            try:
                problem_score, status_str = _evaluate_with_docker(
                    problem_dir, sol_path
                )
            except Exception as e:
                scores[score_key] = Score(value=0.0, name=score_key, explanation=f"error: {e}")
                attempted += 1
                continue

            scores[score_key] = Score(value=problem_score, name=score_key, explanation=status_str)
            total_score += problem_score
            attempted += 1

        # Average over ALL problems, not just attempted ones
        avg_score = total_score / total_problems

        return ScoreBundle(
            scores=scores,
            aggregated=avg_score,
            feedback=f"Solved {attempted}/{total_problems} problems | Average: {avg_score:.4f}",
        )


def _evaluate_with_docker(
    problem_dir: Path, solution_path: Path
) -> tuple[float, str]:
    """Run a solution through the problem's Docker-based evaluator.

    Returns (score, status_string).
    """
    # Read problem config
    config_path = problem_dir / "config.yaml"
    if not config_path.exists():
        return 0.0, "no config.yaml"

    with open(config_path) as f:
        config = yaml.safe_load(f)

    docker_image = config.get("docker_image", "frontier-cs-research")
    timeout = config.get("timeout", DEFAULT_TIMEOUT)
    gpu = config.get("gpu", False)

    # Create temp workspace with problem files + solution
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()

        # Copy problem files (evaluator.py, evaluate.sh, resources/, etc.)
        for item in problem_dir.iterdir():
            dest = workspace / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        # Copy the solution
        shutil.copy2(solution_path, workspace / "solution.py")

        # Build docker command
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{workspace}:/workspace",
            "-w", "/workspace",
        ]
        if gpu:
            cmd.extend(["--gpus", "all"])

        cmd.extend([docker_image, "bash", "evaluate.sh"])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return 0.0, "timeout"

        if result.returncode != 0:
            stderr_tail = result.stderr.strip().split("\n")[-3:]
            return 0.0, f"exit code {result.returncode}: {' '.join(stderr_tail)}"

        # Parse last numeric line of stdout as score
        score = _parse_score_from_output(result.stdout)
        if score is None:
            return 0.0, "no score in output"
        return score, "ok"


def _parse_score_from_output(stdout: str) -> float | None:
    """Extract the last numeric line from stdout as the score."""
    for line in reversed(stdout.strip().split("\n")):
        line = line.strip()
        try:
            return float(line)
        except ValueError:
            continue
    return None


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
