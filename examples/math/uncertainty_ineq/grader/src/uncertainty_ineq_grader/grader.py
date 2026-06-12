"""Uncertainty inequality problem grader.

Evaluates programs that find Hermite polynomial coefficients minimizing the
largest positive root of P(x)/x^2, providing an upper bound for C4.

The program file must define a run() function returning (coeffs, c4_bound, r_max).

Verification uses sympy for exact symbolic computation.
"""

from __future__ import annotations

import json
import os
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle

# Best known C4 upper bound (AlphaEvolve).
BENCHMARK = 0.3215872333529007


class Grader(TaskGrader):
    """Grader for the uncertainty inequality problem.

    Score = BENCHMARK / c4_bound (higher is better, >1 means new record).
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
        c4_bound = result.get("c4_bound", float("inf"))
        r_max = result.get("r_max", 0.0)
        eval_time = result.get("eval_time", 0.0)

        explanation = (
            f"C4 bound: {c4_bound:.10f} | "
            f"r_max: {r_max:.10f} | "
            f"Score: {combined_score:.6f} | "
            f"Time: {eval_time:.1f}s | "
            f"Benchmark: {BENCHMARK}"
        )
        if combined_score > 1.0:
            explanation += " | NEW RECORD!"

        return self.score(combined_score, explanation)


def _run_evaluation(program_path: str, timeout: int, python_cmd: list[str]) -> dict:
    """Run the program in a subprocess with timeout."""
    script = textwrap.dedent(f"""\
        import json, sys, os, time
        import numpy as np
        import sympy as sp

        BENCHMARK = {BENCHMARK!r}

        sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
        module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
        program = __import__(module_name)

        start = time.time()
        try:
            coeffs, c4_bound, r_max = program.run()
        except Exception as e:
            print(json.dumps({{"error": f"run() failed: {{e}}"}}))
            sys.exit(0)
        eval_time = time.time() - start

        coeffs = np.asarray(coeffs, dtype=float)

        # --- Symbolic verification using sympy ---
        x = sp.symbols("x")

        def hermite_4k_polys(m):
            degrees = [4 * k for k in range(m)]
            Hs = [sp.polys.orthopolys.hermite_poly(n=d, x=x, polys=False) for d in degrees]
            return Hs, degrees

        def construct_P_with_forced_zero(input_coeffs):
            m = len(input_coeffs)
            Hs, _ = hermite_4k_polys(m + 1)
            rc = [sp.Rational(c) for c in input_coeffs]
            partial = sum(rc[i] * Hs[i] for i in range(m))
            a = Hs[m].subs(x, 0)
            b = -partial.subs(x, 0)
            c_last = sp.Rational(b) / sp.Rational(a)
            P = partial + c_last * Hs[m]
            if sp.limit(P, x, sp.oo) < 0:
                P = -P
            return sp.simplify(P)

        def largest_positive_root_of_P_over_x2(P):
            gq = sp.exquo(P, x**2)
            roots = sp.real_roots(gq, x)
            if not roots:
                raise ValueError("No real roots for P(x)/x^2.")
            best = None
            for r in roots:
                r_approx = r.eval_rational(n=200)
                eps = sp.Rational(1, 10**198)
                left = gq.subs(x, r_approx - eps)
                right = gq.subs(x, r_approx + eps)
                if (left > 0 and right < 0) or (left < 0 and right > 0):
                    if best is None or r_approx > best:
                        best = r_approx
            if best is None:
                raise ValueError("No root with a verified sign change for P(x)/x^2.")
            return float(best)

        try:
            P = construct_P_with_forced_zero(coeffs)
            assert P.subs(x, 0) == 0, "P(0) != 0 after forcing."
            assert sp.limit(P, x, sp.oo) > 0, "Limit at +inf is not positive."

            rmax = largest_positive_root_of_P_over_x2(P)
            c4 = (rmax**2) / (2.0 * np.pi)

            atol = 1e-9
            rtol = 1e-9
            if not np.isclose(c4, float(c4_bound), rtol=rtol, atol=atol):
                print(json.dumps({{"error": f"C4 mismatch: reported {{c4_bound:.12f}}, recomputed {{c4:.12f}}"}}))
                sys.exit(0)
            if not np.isclose(rmax, float(r_max), rtol=rtol, atol=atol):
                print(json.dumps({{"error": f"r_max mismatch: reported {{r_max:.12f}}, recomputed {{rmax:.12f}}"}}))
                sys.exit(0)

            score = BENCHMARK / c4
            print(json.dumps({{
                "c4_bound": float(c4),
                "combined_score": score,
                "r_max": float(rmax),
                "coeffs": coeffs.tolist(),
                "eval_time": eval_time,
            }}))
        except Exception as e:
            print(json.dumps({{"error": f"Verification failed: {{e}}"}}))
            sys.exit(0)
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
