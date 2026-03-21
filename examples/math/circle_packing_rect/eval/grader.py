"""Circle packing in rectangle grader.

Evaluates programs that pack 21 circles into a rectangle with perimeter 4
to maximize sum of radii. The program file must define a run() function
returning a numpy array of shape (21, 3) where each row is (x, y, radius).
"""

from __future__ import annotations

import json
import os
import sys
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle

NUM_CIRCLES = 21
BENCHMARK = 2.3658321334167627
TOL = 1e-6


class Grader(TaskGrader):
    """Grader for the circle packing in rectangle problem (N=21).

    Score = sum_radii / BENCHMARK (higher is better, >1 means new record).
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

        score = result.get("score", 0.0)
        radii_sum = result.get("radii_sum", 0.0)
        eval_time = result.get("eval_time", 0.0)

        explanation = (
            f"Sum of radii: {radii_sum:.6f} | "
            f"Score: {score:.6f} | "
            f"Time: {eval_time:.1f}s | "
            f"Benchmark: {BENCHMARK:.6f}"
        )
        if score > 1.0:
            explanation += " | NEW RECORD!"

        return self.score(score, explanation)


def _run_evaluation(program_path: str, timeout: int) -> dict:
    """Run the program in a subprocess with timeout."""
    script = textwrap.dedent(f"""\
        import json, sys, os, time
        import numpy as np

        NUM_CIRCLES = {NUM_CIRCLES}
        BENCHMARK = {BENCHMARK!r}
        TOL = {TOL!r}

        sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
        module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
        program = __import__(module_name)

        start = time.time()
        try:
            circles = program.run()
        except Exception as e:
            print(json.dumps({{"error": f"run() failed: {{e}}"}}))
            sys.exit(0)
        eval_time = time.time() - start

        if not isinstance(circles, np.ndarray):
            circles = np.array(circles, dtype=float)
        else:
            circles = circles.astype(float)

        if circles.shape != (NUM_CIRCLES, 3):
            print(json.dumps({{"error": f"Invalid shape: {{circles.shape}}, expected ({{}}, 3)".format(NUM_CIRCLES)}}))
            sys.exit(0)

        if np.isnan(circles).any():
            print(json.dumps({{"error": "NaN values detected"}}))
            sys.exit(0)

        radii = circles[:, 2]

        # Validate radii are non-negative
        for i in range(NUM_CIRCLES):
            if radii[i] < 0:
                print(json.dumps({{"error": f"Circle {{i}} has negative radius {{radii[i]}}"}}))
                sys.exit(0)

        # Validate no overlaps
        for i in range(NUM_CIRCLES):
            for j in range(i + 1, NUM_CIRCLES):
                dist = np.sqrt(np.sum((circles[i, :2] - circles[j, :2]) ** 2))
                if dist < circles[i, 2] + circles[j, 2] - TOL:
                    print(json.dumps({{"error": f"Circles {{i}} and {{j}} overlap: dist={{dist:.6f}}, r1+r2={{circles[i,2]+circles[j,2]:.6f}}"}}))
                    sys.exit(0)

        # Validate circles fit in rectangle with perimeter 4
        # Compute minimum circumscribing rectangle
        min_x = np.min(circles[:, 0] - circles[:, 2])
        max_x = np.max(circles[:, 0] + circles[:, 2])
        min_y = np.min(circles[:, 1] - circles[:, 2])
        max_y = np.max(circles[:, 1] + circles[:, 2])
        width = max_x - min_x
        height = max_y - min_y
        if width + height > 2 + TOL:
            print(json.dumps({{"error": f"Circles not contained in rectangle of perimeter 4: width={{width:.6f}}, height={{height:.6f}}, w+h={{width+height:.6f}} > 2"}}))
            sys.exit(0)

        radii_sum = float(np.sum(radii))
        score = radii_sum / BENCHMARK if BENCHMARK > 0 else 0.0
        print(json.dumps({{"score": score, "radii_sum": radii_sum, "eval_time": eval_time}}))
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
