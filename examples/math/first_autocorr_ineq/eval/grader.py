"""First autocorrelation inequality grader.

Evaluates programs that minimize the C1 constant:
  C1 = max(autoconvolution(f)) / (integral(f))^2

The program file must define a run() function returning
(f_values, c1_achieved, loss, n_points) where:
  - f_values: numpy array of shape (n_points,), non-negative function values
  - c1_achieved: float, the C1 ratio achieved
  - loss: float, the optimization loss
  - n_points: int, number of discretization points
"""

from __future__ import annotations

import json
import os
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle

# Known best C1 upper bound (AlphaEvolve result).
BENCHMARK = 1.5052939684401607


class Grader(TaskGrader):
    """Grader for the first autocorrelation inequality problem.

    Score = BENCHMARK / C1 (higher is better, >1 means new record).
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
        c1 = result.get("c1", 0.0)
        n_points = result.get("n_points", 0)
        eval_time = result.get("eval_time", 0.0)

        explanation = (
            f"C1: {c1:.8f} | "
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
            f_values, c1_achieved, loss, n_points = program.run()
        except Exception as e:
            print(json.dumps({{"error": f"run() failed: {{e}}"}}))
            sys.exit(0)
        eval_time = time.time() - start

        # Validate shape
        if f_values.shape != (n_points,):
            print(json.dumps({{"error": f"Expected shape ({{n_points}},), got {{f_values.shape}}"}}))
            sys.exit(0)

        # Check non-negativity
        if np.any(f_values < 0.0):
            print(json.dumps({{"error": "Function must be non-negative"}}))
            sys.exit(0)

        # Recompute C1 to verify
        dx = 0.5 / n_points
        f_nonneg = np.maximum(f_values, 0.0)
        autoconv = np.convolve(f_nonneg, f_nonneg, mode="full") * dx
        integral_sq = (np.sum(f_nonneg) * dx) ** 2

        if integral_sq < 1e-8:
            print(json.dumps({{"error": "Function integral is too small"}}))
            sys.exit(0)

        computed_c1 = float(np.max(autoconv / integral_sq))

        # Verify consistency
        delta = abs(computed_c1 - c1_achieved)
        if delta > 1e-6:
            print(json.dumps({{"error": f"C1 mismatch: reported {{c1_achieved:.6f}}, computed {{computed_c1:.6f}}, delta: {{delta:.6f}}"}}))
            sys.exit(0)

        score = BENCHMARK / float(c1_achieved)
        print(json.dumps({{
            "c1": float(c1_achieved),
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
