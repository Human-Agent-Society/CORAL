"""Minimizing max-min distance grader (3D, 14 points).

Evaluates programs that place 14 points in 3D to maximize the ratio
(min_distance / max_distance)^2.

The program file must define a run() function returning a numpy array
of shape (14, 3) containing the point coordinates.
"""

from __future__ import annotations

import json
import os
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle

NUM_POINTS = 14
DIMENSION = 3
BENCHMARK = 1 / 4.165849767


class Grader(TaskGrader):
    """Grader for the max-min distance problem (3D, 14 points).

    Score = (min_dist/max_dist)^2 / BENCHMARK (higher is better, >1 means new record).
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
        min_max_ratio = result.get("min_max_ratio", 0.0)
        eval_time = result.get("eval_time", 0.0)

        explanation = (
            f"(min/max)^2: {min_max_ratio:.8f} | "
            f"Score: {score:.6f} | "
            f"Time: {eval_time:.1f}s | "
            f"Benchmark: {BENCHMARK:.8f}"
        )
        if score > 1.0:
            explanation += " | NEW RECORD!"

        return self.score(score, explanation)


def _run_evaluation(program_path: str, timeout: int, python_cmd: list[str]) -> dict:
    """Run the program in a subprocess with timeout and verify the solution."""
    script = textwrap.dedent(f"""\
        import json, sys, os, time
        import numpy as np
        import scipy.spatial.distance

        NUM_POINTS = {NUM_POINTS}
        DIMENSION = {DIMENSION}
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

        if points.shape != (NUM_POINTS, DIMENSION):
            print(json.dumps({{"error": f"Invalid shape: {{points.shape}}, expected ({{NUM_POINTS}}, {{DIMENSION}})"}}))
            sys.exit(0)

        if np.isnan(points).any():
            print(json.dumps({{"error": "NaN values detected in points"}}))
            sys.exit(0)

        pairwise_distances = scipy.spatial.distance.pdist(points)
        min_distance = np.min(pairwise_distances)
        max_distance = np.max(pairwise_distances)

        if max_distance <= 0:
            print(json.dumps({{"error": "Max distance is zero or negative"}}))
            sys.exit(0)

        inv_ratio_squared = (min_distance / max_distance) ** 2
        score = float(inv_ratio_squared / BENCHMARK)

        print(json.dumps({{
            "min_max_ratio": float(inv_ratio_squared),
            "combined_score": score,
            "min_distance": float(min_distance),
            "max_distance": float(max_distance),
            "eval_time": eval_time,
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
