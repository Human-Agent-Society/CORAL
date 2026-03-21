"""Heilbronn triangle grader.

Evaluates programs that place 11 points inside an equilateral triangle to
maximize the minimum triangle area formed by any 3 points.
The program file must define a run() function returning
np.ndarray of shape (11, 2) with point coordinates.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle

NUM_POINTS = 11
BENCHMARK = 0.036529889880030156


class Grader(TaskGrader):
    """Grader for the Heilbronn triangle problem (11 points).

    Score = min_area_normalized / BENCHMARK (higher is better, >1 means new record).
    """

    def evaluate(self) -> ScoreBundle:
        program_file = self.args.get("program_file", "initial_program.py")
        program_path = os.path.join(self.codebase_path, program_file)

        if not os.path.exists(program_path):
            return self.fail(f"Program file not found: {program_file}")

        timeout = self.args.get("timeout", 600)

        try:
            result = _run_evaluation(program_path, timeout)
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


def _run_evaluation(program_path: str, timeout: int) -> dict:
    """Run the program in a subprocess with timeout."""
    script = textwrap.dedent(f"""\
        import json, sys, os, time
        import numpy as np
        import itertools

        NUM_POINTS = {NUM_POINTS}
        BENCHMARK = {BENCHMARK!r}
        TOL = 1e-6

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

        # Check all points are inside the equilateral triangle
        # Vertices: (0,0), (1,0), (0.5, sqrt(3)/2)
        for i, (x, y) in enumerate(points):
            cond1 = y >= -TOL
            cond2 = np.sqrt(3) * x <= np.sqrt(3) - y + TOL
            cond3 = y <= np.sqrt(3) * x + TOL
            if not (cond1 and cond2 and cond3):
                print(json.dumps({{"error": f"Point {{i}} ({{x}}, {{y}}) is outside the equilateral triangle"}}))
                sys.exit(0)

        # Compute triangle area helper
        def triangle_area(a, b, c):
            return abs(a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1])) / 2

        # Equilateral triangle area
        a_tri = np.array([0, 0])
        b_tri = np.array([1, 0])
        c_tri = np.array([0.5, np.sqrt(3) / 2])
        equilateral_area = triangle_area(a_tri, b_tri, c_tri)

        # Min triangle area over all C(11,3) = 165 triples
        min_triangle_area = min(
            triangle_area(p1, p2, p3) for p1, p2, p3 in itertools.combinations(points, 3)
        )
        min_area_normalized = min_triangle_area / equilateral_area
        combined_score = min_area_normalized / BENCHMARK

        print(json.dumps({{
            "min_area_normalized": float(min_area_normalized),
            "combined_score": float(combined_score),
            "eval_time": float(eval_time),
        }}))
    """)
    import subprocess
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-1000:])
    return json.loads(result.stdout)
