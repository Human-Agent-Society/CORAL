"""Erdős minimum overlap problem grader.

Evaluates programs that search for step functions h: [0,2] → [0,1]
minimizing max_k ∫ h(x)(1 - h(x+k)) dx, providing an upper bound for C₅.

The program file must define a run() function returning (h_values, c5_bound, n_points).
"""

from __future__ import annotations

import asyncio
import json
import os
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle

# Best known upper bound for C₅
BENCHMARK = 0.380871


class Grader(TaskGrader):
    """Grader for the Erdős minimum overlap problem.

    Score = BENCHMARK / c5_bound (higher is better, >1 means new record).
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

        combined_score = result.get("combined_score", 0.0)
        c5_bound = result.get("c5_bound", float("inf"))
        n_points = result.get("n_points", 0)
        eval_time = result.get("eval_time", 0.0)

        explanation = (
            f"C₅ bound: {c5_bound:.10f} | "
            f"Score: {combined_score:.6f} | "
            f"n_points: {n_points} | "
            f"Time: {eval_time:.1f}s | "
            f"Benchmark: {BENCHMARK:.10f}"
        )
        if combined_score > 1.0:
            explanation += " | NEW RECORD!"

        return self.score(combined_score, explanation)


def _run_evaluation(program_path: str, timeout: int, python_cmd: list[str]) -> dict:
    """Run the program in a subprocess with timeout."""
    script = textwrap.dedent(f"""\
        import json, sys, os, time
        sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
        module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
        program = __import__(module_name)
        start = time.time()
        h_values, c5_bound, n_points = program.run()
        eval_time = time.time() - start
        import numpy as np
        h = np.array(h_values)
        if h.shape != (n_points,):
            raise ValueError(f"Expected h shape ({{n_points}},), got {{h.shape}}")
        if np.any(h < 0) or np.any(h > 1):
            raise ValueError(f"h(x) not in [0,1]. Range: [{{h.min()}}, {{h.max()}}]")
        dx = 2.0 / n_points
        integral_h = np.sum(h) * dx
        if not np.isclose(integral_h, 1.0, atol=1e-3):
            raise ValueError(f"Integral of h is not close to 1. Got: {{integral_h:.6f}}")
        j = 1.0 - h
        correlation = np.correlate(h, j, mode="full") * dx
        computed_c5 = np.max(correlation)
        if not np.isclose(computed_c5, float(c5_bound), atol=1e-4):
            raise ValueError(f"C5 mismatch: reported {{c5_bound:.6f}}, computed {{computed_c5:.6f}}")
        print(json.dumps({{
            "c5_bound": float(c5_bound),
            "combined_score": {BENCHMARK} / float(c5_bound),
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
