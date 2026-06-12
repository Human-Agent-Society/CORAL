"""CORAL grader for the Prism LLM model placement task.

No external data files required — test cases are generated procedurally.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from coral.grader import TaskGrader
from coral.types import ScoreBundle


class Grader(TaskGrader):
    def evaluate(self) -> ScoreBundle:
        program_file = self.args.get("program_file", "initial_program.py")
        program_path = os.path.join(self.codebase_path, program_file)

        if not os.path.exists(program_path):
            return self.fail(f"Program file not found: {program_file}")

        eval_dir = str(Path(self.private_dir) / "eval")
        if eval_dir not in sys.path:
            sys.path.insert(0, eval_dir)

        try:
            spec = importlib.util.spec_from_file_location(
                "prism_evaluator", str(Path(eval_dir) / "evaluator.py")
            )
            evaluator_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(evaluator_mod)

            result = evaluator_mod.evaluate(program_path)

            if "error" in result:
                return self.fail(result["error"])

            combined_score = float(result.get("combined_score", 0.0))
            max_kvpr = result.get("max_kvpr", 0.0)
            success_rate = result.get("success_rate", 0.0)

            explanation = (
                f"combined={combined_score:.4f} | "
                f"avg_inv_kvpr={max_kvpr:.4f} | "
                f"success_rate={success_rate:.2%}"
            )
            return self.score(combined_score, explanation)

        except Exception as e:
            return self.fail(f"Evaluation error: {e}")
