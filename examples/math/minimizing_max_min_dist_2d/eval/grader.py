"""Minimizing max-min distance 2D grader.

Evaluates programs that place 16 points in 2D to maximize (min_dist/max_dist)^2
over all pairwise distances.
The program file must define a run() function returning
np.ndarray of shape (16, 2) with point coordinates.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle

NUM_POINTS = 16
DIMENSION = 2
BENCHMARK = 1 / 12.889266112


class Grader(TaskGrader):
    """Grader for the min max-min distance problem (16 points, 2D).

    Score = (min_dist/max_dist)^2 / BENCHMARK (higher is better, >1 means new record).
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
        min_max_ratio = result.get("min_max_ratio", 0.0)
        eval_time = result.get("eval_time", 0.0)

        explanation = (
            f"(min_dist/max_dist)^2: {min_max_ratio:.8f} | "
            f"Score: {score:.6f} | "
            f"Time: {eval_time:.1f}s | "
            f"Benchmark: {BENCHMARK:.10f}"
        )
        if score > 1.0:
            explanation += " | NEW RECORD!"

        return self.score(score, explanation)


def _run_evaluation(program_path: str, timeout: int) -> dict:
    """Run the program in a subprocess with timeout."""
    script = textwrap.dedent(f"""\
        import json, sys, os, time
        import numpy as np
        import scipy.spatial.distance

        NUM_POINTS = {NUM_POINTS}
        DIMENSION = {DIMENSION}
        BENCHMARK = 1 / 12.889266112

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

        if points.shape != (NUM_POINTS, DIMENSION):
            print(json.dumps({{"error": f"Invalid shape: {{points.shape}}, expected ({NUM_POINTS}, {DIMENSION})"}}))
            sys.exit(0)

        pairwise_distances = scipy.spatial.distance.pdist(points)
        min_distance = np.min(pairwise_distances)
        max_distance = np.max(pairwise_distances)

        inv_ratio_squared = (min_distance / max_distance) ** 2 if max_distance > 0 else 0
        combined_score = inv_ratio_squared / BENCHMARK

        print(json.dumps({{
            "min_max_ratio": float(inv_ratio_squared),
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
