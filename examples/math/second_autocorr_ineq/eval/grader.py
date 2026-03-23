"""Second autocorrelation inequality grader.

Evaluates programs that maximize the C2 constant:
  C2 = ||f*f||_2^2 / (||f*f||_1 * ||f*f||_inf)

using the unitless, piecewise-linear integral method.

The program file must define a run() function returning
(f_values, c2_achieved, loss, n_points) where:
  - f_values: numpy array of shape (n_points,), non-negative function values
  - c2_achieved: float, the C2 ratio achieved
  - loss: float, the optimization loss
  - n_points: int, number of discretization points
"""

from __future__ import annotations

import json
import os
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle

# Known best C2 lower bound (AlphaEvolve result).
BENCHMARK = 0.8962799441554086


class Grader(TaskGrader):
    """Grader for the second autocorrelation inequality problem.

    Score = C2_verified / BENCHMARK (higher is better, >1 means new record).
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
        c2 = result.get("c2", 0.0)
        n_points = result.get("n_points", 0)
        eval_time = result.get("eval_time", 0.0)

        explanation = (
            f"C2: {c2:.8f} | "
            f"Score: {score:.6f} | "
            f"N: {n_points} | "
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

        BENCHMARK = {BENCHMARK!r}

        sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
        module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
        program = __import__(module_name)

        start = time.time()
        try:
            f_values, c2_achieved_from_opt, loss, n_points = program.run()
        except Exception as e:
            print(json.dumps({{"error": f"run() failed: {{e}}"}}))
            sys.exit(0)
        eval_time = time.time() - start

        # Validate shape
        if f_values.shape != (n_points,):
            print(json.dumps({{"error": f"Expected shape ({{n_points}},), got {{f_values.shape}}"}}))
            sys.exit(0)

        # Check non-negativity (allow small floating point errors)
        if np.any(f_values < -1e-6):
            print(json.dumps({{"error": "Function must be non-negative"}}))
            sys.exit(0)

        f_nonneg = np.maximum(f_values, 0.0)

        # Compute the raw, unscaled convolution
        convolution = np.convolve(f_nonneg, f_nonneg, mode="full")

        # L2 norm squared via piecewise linear integration
        num_conv_points = len(convolution)
        x_points = np.linspace(-0.5, 0.5, num_conv_points + 2)
        x_intervals = np.diff(x_points)
        y_points = np.concatenate(([0], convolution, [0]))
        l2_norm_squared = 0.0
        for i in range(len(convolution) + 1):
            y1, y2, h = y_points[i], y_points[i + 1], x_intervals[i]
            interval_l2_squared = (h / 3) * (y1**2 + y1 * y2 + y2**2)
            l2_norm_squared += interval_l2_squared

        # L1 norm
        norm_1 = np.sum(np.abs(convolution)) / (len(convolution) + 1)

        # Infinity norm
        norm_inf = np.max(np.abs(convolution))

        if norm_1 * norm_inf < 1e-15:
            print(json.dumps({{"error": "Convolution norms are too small"}}))
            sys.exit(0)

        c2_verified = l2_norm_squared / (norm_1 * norm_inf)

        score = float(c2_verified) / BENCHMARK
        print(json.dumps({{
            "c2": float(c2_verified),
            "combined_score": score,
            "loss": float(loss),
            "n_points": int(n_points),
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
