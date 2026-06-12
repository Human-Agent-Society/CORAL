"""CORAL grader for the Transaction Scheduling makespan minimization task.

No external data files required — workloads are defined in workloads.py.
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
        # txn evaluator uses __file__ to add its own dir to sys.path for
        # importing workloads and txn_simulator — ensure it's on sys.path too.
        if eval_dir not in sys.path:
            sys.path.insert(0, eval_dir)

        try:
            spec = importlib.util.spec_from_file_location(
                "txn_evaluator", str(Path(eval_dir) / "evaluator.py")
            )
            evaluator_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(evaluator_mod)

            result = evaluator_mod.evaluate(program_path, python_cmd=self.get_python_command())

            combined_score = float(result.get("combined_score", 0.0))
            makespan = result.get("makespan", 0.0)
            validity = result.get("validity", 0.0)

            if combined_score == 0.0 and validity == 0.0:
                error = result.get("error", "unknown error")
                return self.fail(f"Evaluation failed: {error}")

            explanation = (
                f"combined={combined_score:.2f} | "
                f"makespan={makespan:.2f} | "
                f"valid={'yes' if validity == 1.0 else 'no'}"
            )
            return self.score(combined_score, explanation)

        except Exception as e:
            return self.fail(f"Evaluation error: {e}")
