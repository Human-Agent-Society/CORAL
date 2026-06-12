"""Heilbronn convex 13 grader.

Evaluates programs that place 13 points in 2D to maximize the minimum triangle
area (normalized by convex hull area) formed by any 3 of the 13 points.
The program file must define a run() function returning
np.ndarray of shape (13, 2) with point coordinates.
"""

from __future__ import annotations

import json
import os
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle

NUM_POINTS = 13
BENCHMARK = 0.030936889034895654


class Grader(TaskGrader):
    """Grader for the Heilbronn convex problem (13 points).

    Score = (min_triangle_area / convex_hull_area) / BENCHMARK (higher is better, >1 means new record).
    """

    def evaluate(self) -> ScoreBundle:
        program_file = self.args.get("program_file", "initial_program.py")
        program_path = os.path.join(self.codebase_path, program_file)

        if not os.path.exists(program_path):
            return self.fail(f"Program file not found: {program_file}")

        timeout = self.timeout

        try:
            result = _run_evaluation(program_path, timeout, self.get_python_command())
        except TimeoutError:
            return self.fail(f"Evaluation timed out after {timeout}s")
        except Exception as e:
            return self.fail(f"Evaluation failed: {e}")

        if "error" in result:
            return self.fail(f"Error: {result['error']}")

        score = result.get("combined_score", 0.0)
        min_area_normalized = result.get("min_area_normalized", 0.0)
        eval_time = result.get("eval_time", 0.0)

        explanation = (
            f"Min area normalized: {min_area_normalized:.8f} | "
            f"Score: {score:.6f} | "
            f"Time: {eval_time:.1f}s | "
            f"Benchmark: {BENCHMARK}"
        )
        if score > 1.0:
            explanation += " | NEW RECORD!"

        return self.score(score, explanation)


def _run_evaluation(program_path: str, timeout: int, python_cmd: list[str]) -> dict:
    """Run the program in a subprocess with timeout."""
    script = textwrap.dedent(f"""\
        import json, sys, os, time
        import numpy as np
        import itertools
        from scipy.spatial import ConvexHull

        NUM_POINTS = {NUM_POINTS}
        BENCHMARK = {BENCHMARK!r}

        sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
        module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
        program = __import__(module_name)

        start = time.time()
        try:
            points = program.run()
        except Exception as e:
            print(json.dumps({{"error": f"run() failed: {{e}}"}}))
            sys.exit(0)
        eval_time = time.time() - start

        if not isinstance(points, np.ndarray):
            points = np.array(points)

        if points.shape != (NUM_POINTS, 2):
            print(json.dumps({{"error": f"Invalid shape: {{points.shape}}, expected ({NUM_POINTS}, 2)"}}))
            sys.exit(0)

        # Compute triangle area helper
        def triangle_area(p1, p2, p3):
            return abs(p1[0] * (p2[1] - p3[1]) + p2[0] * (p3[1] - p1[1]) + p3[0] * (p1[1] - p2[1])) / 2

        # Min triangle area over all C(13,3) = 286 triples
        min_triangle_area = min(
            triangle_area(p1, p2, p3) for p1, p2, p3 in itertools.combinations(points, 3)
        )

        # Normalize by convex hull area
        convex_hull_area = ConvexHull(points).volume
        min_area_normalized = min_triangle_area / convex_hull_area
        combined_score = min_area_normalized / BENCHMARK

        print(json.dumps({{
            "min_area_normalized": float(min_area_normalized),
            "combined_score": float(combined_score),
            "eval_time": float(eval_time),
        }}))
    """)
    import subprocess
    result = subprocess.run(
        [*python_cmd, "-c", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-2000:])
    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(
            f"Script produced no output.\nstderr: {result.stderr.strip()[-1000:]}"
        )
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        # Handle stdout pollution from print statements
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        raise RuntimeError(
            f"No valid JSON in output.\nstdout: {stdout[-500:]}\nstderr: {result.stderr.strip()[-500:]}"
        )
