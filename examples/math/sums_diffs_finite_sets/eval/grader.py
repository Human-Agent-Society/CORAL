"""Sums and differences of finite sets grader.

Evaluates programs that search for a finite set U of non-negative integers
(containing 0) that maximizes C6 = 1 + log(|U-U|/|U+U|) / log(2*max(U)+1).

The program file must define a run() function returning (u_set, c6_bound).
"""

from __future__ import annotations

import json
import os
import sys
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle

# Best known C6 lower bound (AlphaEvolve).
BENCHMARK = 1.158417281556896


class Grader(TaskGrader):
    """Grader for the sums and differences of finite sets problem.

    Score = c6_bound / BENCHMARK (higher is better, >1 means new record).
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

        combined_score = result.get("combined_score", 0.0)
        c6_bound = result.get("c6_bound", 0.0)
        set_size = result.get("set_size", 0)
        max_val = result.get("max_val", 0)
        eval_time = result.get("eval_time", 0.0)

        explanation = (
            f"C6 bound: {c6_bound:.10f} | "
            f"Score: {combined_score:.6f} | "
            f"|U|: {set_size} | "
            f"max(U): {max_val} | "
            f"Time: {eval_time:.1f}s | "
            f"Benchmark: {BENCHMARK}"
        )
        if combined_score > 1.0:
            explanation += " | NEW RECORD!"

        return self.score(combined_score, explanation)


def _run_evaluation(program_path: str, timeout: int) -> dict:
    """Run the program in a subprocess with timeout."""
    script = textwrap.dedent(f"""\
        import json, sys, os, time
        import numpy as np

        BENCHMARK = {BENCHMARK!r}

        sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
        module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
        program = __import__(module_name)

        start = time.time()
        try:
            u_set, c6_bound = program.run()
        except Exception as e:
            print(json.dumps({{"error": f"run() failed: {{e}}"}}))
            sys.exit(0)
        eval_time = time.time() - start

        u_set = np.array(u_set, dtype=int)

        # Validate: must be a 1D array
        if u_set.ndim != 1:
            print(json.dumps({{"error": "Solution U must be a 1D numpy array of integers."}}))
            sys.exit(0)

        # Validate: must contain 0
        if 0 not in u_set:
            print(json.dumps({{"error": "Set U must contain 0."}}))
            sys.exit(0)

        # Validate: all non-negative
        if np.any(u_set < 0):
            print(json.dumps({{"error": "Set U must contain non-negative integers."}}))
            sys.exit(0)

        # Recompute C6
        u_plus_u = np.unique(u_set[:, None] + u_set[None, :])
        u_minus_u = np.unique(u_set[:, None] - u_set[None, :])

        size_U_plus_U = len(u_plus_u)
        size_U_minus_U = len(u_minus_u)
        max_U = int(np.max(u_set))

        if max_U == 0:
            print(json.dumps({{"error": "max(U) is 0, trivial set."}}))
            sys.exit(0)

        ratio = size_U_minus_U / size_U_plus_U
        log_ratio = np.log(ratio)
        log_denom = np.log(2 * max_U + 1)
        computed_c6 = 1 + log_ratio / log_denom

        # Verify consistency
        if not np.isclose(computed_c6, float(c6_bound)):
            print(json.dumps({{"error": f"C6 mismatch: reported {{c6_bound:.6f}}, computed {{computed_c6:.6f}}"}}))
            sys.exit(0)

        score = float(c6_bound) / BENCHMARK
        print(json.dumps({{
            "c6_bound": float(c6_bound),
            "combined_score": score,
            "set_size": len(u_set),
            "max_val": max_U,
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
