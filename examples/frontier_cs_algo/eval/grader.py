"""Frontier-CS Algorithmic batch grader.

Evaluates all C++ solutions found in solutions/ against a go-judge server.
Returns the average score across all attempted problems.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from coral.grader import TaskGrader
from coral.types import Score, ScoreBundle

POLL_INTERVAL = 2
POLL_TIMEOUT = 1000


class Grader(TaskGrader):
    """Batch grader for Frontier-CS algorithmic problems.

    Scans solutions/ for .cpp files, submits each to a go-judge server,
    and returns the average score. Problems without solutions are skipped.
    """

    def evaluate(self) -> ScoreBundle:
        judge_url = self.args.get("judge_url", "http://localhost:8081")

        # Count total problems from the seed's problems/ directory
        problems_dir = Path(self.codebase_path) / "problems"
        if not problems_dir.exists():
            return self.fail("problems/ directory not found in codebase")

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
                problem_score, status_str = _submit_and_poll(judge_url, problem_id, code)
            except Exception as e:
                scores[f"problem_{problem_id}"] = Score(
                    value=0.0, name=f"problem_{problem_id}",
                )
                lines.append(f"problem {problem_id}: 0.00 (error: {e})")
                attempted += 1
                continue

            scores[f"problem_{problem_id}"] = Score(
                value=problem_score, name=f"problem_{problem_id}",
            )
            total_score += problem_score
            attempted += 1
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


def _submit_and_poll(
    judge_url: str, problem_id: str, code: str
) -> tuple[float, str]:
    """Submit code to the judge and poll for results.

    Returns (score, status_string).
    """
    # Submit
    payload = json.dumps({
        "pid": problem_id,
        "code": code,
        "lang": "cpp",
    }).encode()
    req = urllib.request.Request(
        f"{judge_url}/submit",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            submit_data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return 0.0, f"submit failed ({e.code}): pid={problem_id}"
    submission_id = submit_data["submission_id"]

    # Poll for result
    deadline = time.monotonic() + POLL_TIMEOUT
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{judge_url}/result/{submission_id}") as resp:
                result_data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return 0.0, f"poll failed ({e.code}): submission_id={submission_id}"

        status = result_data.get("status", "")
        if status == "done":
            score = float(result_data.get("score", 0.0))
            return score, "ok"
        if status == "error":
            error_msg = result_data.get("message", "unknown error")
            return 0.0, f"error: {error_msg}"

        time.sleep(POLL_INTERVAL)

    return 0.0, "timeout"
