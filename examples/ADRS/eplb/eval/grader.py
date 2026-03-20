"""CORAL grader for the EPLB (Expert Parallelism Load Balancer) task.

Wraps the skydiscover evaluator. Expects expert-load.json to be present
alongside this file in the eval/ directory.

Setup:
    wget https://huggingface.co/datasets/abmfy/eplb-openevolve/resolve/main/expert-load.json
    cp expert-load.json examples/ADRS/eplb/eval/expert-load.json
"""

from __future__ import annotations

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

        # The evaluator uses __file__ to locate expert-load.json, so it must
        # be imported from its actual location in .coral/private/eval/.
        eval_dir = str(Path(self.private_dir) / "eval")
        if eval_dir not in sys.path:
            sys.path.insert(0, eval_dir)

        data_file = Path(eval_dir) / "expert-load.json"
        if not data_file.exists():
            return self.fail(
                "expert-load.json not found. Download it and place it in "
                "examples/ADRS/eplb/eval/expert-load.json:\n"
                "  wget https://huggingface.co/datasets/abmfy/eplb-openevolve"
                "/resolve/main/expert-load.json"
            )

        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "eplb_evaluator", str(Path(eval_dir) / "evaluator.py")
            )
            evaluator_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(evaluator_mod)

            NUM_RUNS = 3
            results = []
            for _ in range(NUM_RUNS):
                result = evaluator_mod.evaluate(program_path)
                if "error" in result:
                    return self.fail(result["error"])
                results.append(result)

            avg = lambda key: sum(r.get(key, 0.0) for r in results) / NUM_RUNS
            combined_score = avg("combined_score")
            bal_gpu = avg("balancedness_score_gpu")
            bal_expert = avg("balancedness_score_expert")
            speed = avg("speed_score")
            t_algo = avg("times_algorithm")
            t_infer = avg("times_inference")

            explanation = (
                f"combined={combined_score:.4f} | "
                f"bal_expert={bal_expert:.4f} | bal_gpu={bal_gpu:.4f} | "
                f"speed={speed:.4f} | t_algo={t_algo:.4f}s | t_infer={t_infer:.4f}s"
            )
            return self.score(combined_score, explanation)

        except Exception as e:
            return self.fail(f"Evaluation error: {e}")
