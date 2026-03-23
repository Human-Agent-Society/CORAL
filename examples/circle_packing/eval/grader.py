"""Circle packing grader.

Evaluates programs that pack 26 circles into a unit square to maximize sum of radii.
The program file must define a run() function returning
(centers, radii, sum_radii) where:
  - centers: numpy array of shape (26, 2) with circle centers
  - radii: numpy array of shape (26,) with radius of each circle
  - sum_radii: float, sum of all radii
"""

from __future__ import annotations

import json
import os
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle

# Best known sum of radii for 26 circles in a unit square (AlphaEvolve).
N = 26
BENCHMARK = 2.635977


class Grader(TaskGrader):
    """Grader for the circle packing problem (N=26).

    Score = sum_radii / BENCHMARK (higher is better, >1 means new record).
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

        score = result.get("score", 0.0)
        sum_radii = result.get("sum_radii", 0.0)
        eval_time = result.get("eval_time", 0.0)

        explanation = (
            f"Sum of radii: {sum_radii:.6f} | "
            f"Score: {score:.6f} | "
            f"Time: {eval_time:.1f}s | "
            f"Benchmark: {BENCHMARK:.6f}"
        )
        if score > 1.0:
            explanation += " | NEW RECORD!"

        return self.score(score, explanation)


def _run_evaluation(program_path: str, timeout: int, python_cmd: list[str]) -> dict:
    """Run the program in a subprocess with timeout."""
    script = textwrap.dedent(f"""\
        import json, sys, os, time
        import numpy as np

        N = {N}
        BENCHMARK = {BENCHMARK!r}

        sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
        module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
        program = __import__(module_name)

        start = time.time()
        try:
            result = program.run()
            centers, radii, sum_radii = result
        except Exception as e:
            print(json.dumps({{"error": f"run() failed: {{e}}"}}))
            sys.exit(0)
        eval_time = time.time() - start

        centers = np.array(centers, dtype=float)
        radii = np.array(radii, dtype=float)

        if np.isnan(centers).any() or np.isnan(radii).any():
            print(json.dumps({{"score": 0.0, "details": "NaN values detected", "eval_time": eval_time}}))
            sys.exit(0)
        if centers.shape != (N, 2):
            print(json.dumps({{"score": 0.0, "details": f"INVALID centers shape {{centers.shape}}, expected ({{N}}, 2)", "eval_time": eval_time}}))
            sys.exit(0)
        if radii.shape != (N,):
            print(json.dumps({{"score": 0.0, "details": f"INVALID radii shape {{radii.shape}}, expected ({{N}},)", "eval_time": eval_time}}))
            sys.exit(0)
        if np.any(radii < 0):
            print(json.dumps({{"score": 0.0, "details": "Negative radii detected", "eval_time": eval_time}}))
            sys.exit(0)

        # Check boundary constraints: each circle must be within the unit square
        for i in range(N):
            x, y = centers[i]
            r = radii[i]
            if x - r < -1e-6 or y - r < -1e-6 or x + r > 1.0 + 1e-6 or y + r > 1.0 + 1e-6:
                print(json.dumps({{"score": 0.0, "details": f"circle {{i}} (center=({{x:.6f}}, {{y:.6f}}), r={{r:.6f}}) outside unit square", "eval_time": eval_time}}))
                sys.exit(0)

        # Check non-overlap: pairwise center distance must be >= sum of radii
        for i in range(N):
            for j in range(i + 1, N):
                dist = np.sqrt(np.sum((centers[i] - centers[j]) ** 2))
                min_allowed = radii[i] + radii[j]
                if dist < min_allowed - 1e-6:
                    print(json.dumps({{"score": 0.0, "details": f"overlap between circles {{i}} and {{j}}: dist={{dist:.6f}} < r_i+r_j={{min_allowed:.6f}}", "eval_time": eval_time}}))
                    sys.exit(0)

        actual_sum = float(np.sum(radii))
        score = actual_sum / BENCHMARK if BENCHMARK > 0 else 0.0
        print(json.dumps({{"score": score, "sum_radii": actual_sum, "eval_time": eval_time}}))
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
