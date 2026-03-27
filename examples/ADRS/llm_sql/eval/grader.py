"""CORAL grader for the LLM-SQL column reordering task.

Wraps the skydiscover evaluator. Requires CSV datasets in eval/datasets/:
  - movies.csv, beer.csv, BIRD.csv, PDMX.csv, products.csv

Setup (from skydiscover repo):
    cd benchmarks/ADRS/llm_sql/evaluator && bash download_dataset.sh
    cp -r datasets/ <coral_repo>/examples/ADRS/llm_sql/eval/
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

        datasets_dir = Path(eval_dir) / "datasets"
        if not datasets_dir.exists():
            return self.fail(
                "Datasets not found. Run download_dataset.sh from the skydiscover "
                "llm_sql evaluator directory, then copy datasets/ into "
                "examples/ADRS/llm_sql/eval/"
            )

        # Add eval dir so evaluator can import utils and solver
        if eval_dir not in sys.path:
            sys.path.insert(0, eval_dir)
        # Add codebase path so evaluator can import initial_program
        if self.codebase_path not in sys.path:
            sys.path.insert(0, self.codebase_path)

        try:
            spec = importlib.util.spec_from_file_location(
                "llm_sql_evaluator", str(Path(eval_dir) / "evaluator.py")
            )
            evaluator_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(evaluator_mod)

            result = evaluator_mod.evaluate(program_path)

            if "error" in result:
                return self.fail(result["error"])

            combined_score = float(result.get("combined_score", 0.0))
            hit_rates = result.get("hit_rates", [])
            runtime = result.get("total_runtime", 0.0)

            explanation = (
                f"combined={combined_score:.4f} | "
                f"avg_hit_rate={sum(hit_rates)/len(hit_rates):.4f} | "
                f"total_runtime={runtime:.2f}s"
            ) if hit_rates else f"combined={combined_score:.4f}"
            return self.score(combined_score, explanation)

        except Exception as e:
            return self.fail(f"Evaluation error: {e}")
