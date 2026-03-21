"""Third autocorrelation inequality grader.

Evaluates programs that minimize the C3 constant:
  C3 = max(|autoconvolution(f)|) / (integral(f))^2

Unlike C1, f is NOT required to be non-negative for C3, and we take
the maximum of the absolute value of the autoconvolution.

The program file must define a run() function returning
(f_values, c3_achieved, loss, n_points) where:
  - f_values: numpy array of shape (n_points,), function values (may be negative)
  - c3_achieved: float, the C3 ratio achieved
  - loss: float, the optimization loss
  - n_points: int, number of discretization points
"""

from __future__ import annotations

import json
import os
import sys
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle

# Known best C3 upper bound (AlphaEvolve result).
BENCHMARK = 1.4556427953745406


class Grader(TaskGrader):
    """Grader for the third autocorrelation inequality problem.

    Score = BENCHMARK / C3 (higher is better, >1 means new record).
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
        c3 = result.get("c3", 0.0)
        n_points = result.get("n_points", 0)
        eval_time = result.get("eval_time", 0.0)

        explanation = (
            f"C3: {c3:.8f} | "
            f"Score: {score:.6f} | "
            f"N: {n_points} | "
            f"Time: {eval_time:.1f}s | "
            f"Benchmark: {BENCHMARK:.8f}"
        )
        if score > 1.0:
            explanation += " | NEW RECORD!"

        return self.score(score, explanation)


def _run_evaluation(program_path: str, timeout: int) -> dict:
    """Run the program in a subprocess with timeout and verify the solution."""
    script = textwrap.dedent(f"""\
        import json, sys, os, time
        import numpy as np

        BENCHMARK = {BENCHMARK!r}

        sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
        module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
        program = __import__(module_name)

        start = time.time()
        try:
            f_values, c3_achieved, loss, n_points = program.run()
        except Exception as e:
            print(json.dumps({{"error": f"run() failed: {{e}}"}}))
            sys.exit(0)
        eval_time = time.time() - start

        # Validate shape
        if f_values.shape != (n_points,):
            print(json.dumps({{"error": f"Expected shape ({{n_points}},), got {{f_values.shape}}"}}))
            sys.exit(0)

        # Recompute C3 to verify
        dx = 0.5 / n_points
        integral_f_sq = (np.sum(f_values) * dx) ** 2

        if integral_f_sq < 1e-9:
            print(json.dumps({{"error": "Function integral is close to zero, ratio is unstable"}}))
            sys.exit(0)

        conv = np.convolve(f_values, f_values, mode="full")
        scaled_conv = conv * dx
        max_abs_conv = np.max(np.abs(scaled_conv))
        computed_c3 = max_abs_conv / integral_f_sq

        # Verify consistency
        delta = abs(computed_c3 - c3_achieved)
        if delta > 1e-3:
            print(json.dumps({{"error": f"C3 mismatch: reported {{c3_achieved:.6f}}, computed {{computed_c3:.6f}}, delta: {{delta:.6f}}"}}))
            sys.exit(0)

        score = BENCHMARK / float(c3_achieved)
        print(json.dumps({{
            "c3": float(c3_achieved),
            "combined_score": score,
            "loss": float(loss),
            "n_points": int(n_points),
            "eval_time": eval_time,
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
