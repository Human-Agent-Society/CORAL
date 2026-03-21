"""Matrix multiplication tensor decomposition grader.

Evaluates programs that find low-rank decompositions of the matrix multiplication
tensor for <n=2, m=4, p=5>. The program file must define a run() function returning
(decomposition, n, m, p, loss, rank) where:
  - decomposition: tuple of three numpy arrays (U, V, W)
  - n, m, p: integers (2, 4, 5)
  - loss: float, final reconstruction loss
  - rank: int, the rank R used
"""

from __future__ import annotations

import json
import os
import sys
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle

# Best known rank for (2,4,5) matrix multiplication tensor (AlphaEvolve).
BENCHMARK = 32


class Grader(TaskGrader):
    """Grader for the matrix multiplication tensor decomposition problem.

    Score = BENCHMARK / rank (higher is better, >1 means new record).
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
        rank = result.get("rank", 0)
        loss = result.get("loss", 0.0)
        eval_time = result.get("eval_time", 0.0)

        explanation = (
            f"Rank: {rank} | "
            f"Score: {combined_score:.6f} | "
            f"Loss: {loss:.2e} | "
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

        BENCHMARK = {BENCHMARK}

        sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
        module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
        program = __import__(module_name)

        start = time.time()
        try:
            result = program.run()
            decomposition, n, m, p, loss, rank = result
        except Exception as e:
            print(json.dumps({{"error": f"run() failed: {{e}}"}}))
            sys.exit(0)
        eval_time = time.time() - start

        # Validate decomposition is a tuple of numpy arrays
        if not isinstance(decomposition, (tuple, list)) or len(decomposition) != 3:
            print(json.dumps({{"error": "Decomposition must be a tuple of 3 numpy arrays"}}))
            sys.exit(0)
        if not all(isinstance(arr, np.ndarray) for arr in decomposition):
            print(json.dumps({{"error": "Decomposition must contain numpy arrays"}}))
            sys.exit(0)
        if any(arr.size == 0 for arr in decomposition):
            print(json.dumps({{"error": "Decomposition arrays must not be empty"}}))
            sys.exit(0)

        U, V, W = decomposition

        # Check factor matrix shapes
        if U.shape != (n * m, rank):
            print(json.dumps({{"error": f"U shape {{U.shape}} != expected ({{n * m}}, {{rank}})"}}))
            sys.exit(0)
        if V.shape != (m * p, rank):
            print(json.dumps({{"error": f"V shape {{V.shape}} != expected ({{m * p}}, {{rank}})"}}))
            sys.exit(0)
        if W.shape != (n * p, rank):
            print(json.dumps({{"error": f"W shape {{W.shape}} != expected ({{n * p}}, {{rank}})"}}))
            sys.exit(0)

        # Construct the ground truth matrix multiplication tensor
        matmul_tensor = np.zeros((n * m, m * p, n * p), dtype=np.float32)
        for i in range(n):
            for j in range(m):
                for k in range(p):
                    matmul_tensor[i * m + j, j * p + k, k * n + i] = 1

        # Reconstruct tensor from decomposition
        reconstructed = np.einsum("ir,jr,kr->ijk", U, V, W)

        # Exact equality check
        if not np.array_equal(reconstructed, matmul_tensor):
            diff = np.max(np.abs(reconstructed - matmul_tensor))
            print(json.dumps({{"error": f"Reconstructed tensor does not exactly match ground truth. Max difference: {{diff:.6e}}"}}))
            sys.exit(0)

        # Loss threshold warning
        if loss > 1e-6:
            pass  # Loss is above threshold but decomposition is exact, so we accept it

        combined_score = BENCHMARK / rank
        print(json.dumps({{
            "combined_score": combined_score,
            "loss": float(loss),
            "rank": int(rank),
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
