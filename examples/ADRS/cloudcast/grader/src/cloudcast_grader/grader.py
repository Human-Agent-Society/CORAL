"""CORAL grader for the Cloudcast multi-cloud broadcast optimization task.

Wraps the skydiscover evaluator. Requires dataset files to be present in eval/:
  - profiles/cost.csv
  - profiles/throughput.csv
  - examples/config/intra_aws.json (and other config JSONs)

Setup (from skydiscover repo):
    cd benchmarks/ADRS/cloudcast/evaluator && bash download_dataset.sh
    cp -r profiles/ examples/ <coral_repo>/examples/ADRS/cloudcast/eval/
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
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

        # Check required data files
        profiles_dir = Path(eval_dir) / "profiles"
        configs_dir = Path(eval_dir) / "examples" / "config"
        if not profiles_dir.exists() or not configs_dir.exists():
            return self.fail(
                "Dataset files not found. Run download_dataset.sh from the skydiscover "
                "cloudcast evaluator directory, then copy profiles/ and examples/ into "
                "examples/ADRS/cloudcast/eval/"
            )

        # Add eval dir to path so evaluator can import broadcast, simulator, utils.
        # Also add codebase path so evaluator can import initial_program (used as fallback).
        for p in [eval_dir, self.codebase_path]:
            if p not in sys.path:
                sys.path.insert(0, p)

        try:
            # Load evaluator from eval dir
            spec = importlib.util.spec_from_file_location(
                "cloudcast_evaluator", str(Path(eval_dir) / "evaluator.py")
            )
            evaluator_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(evaluator_mod)

            # The evaluator writes paths/ and evals/ relative to CWD.
            # Run it in a temp dir to avoid polluting the workspace.
            with tempfile.TemporaryDirectory() as tmpdir:
                orig_dir = os.getcwd()
                try:
                    os.chdir(tmpdir)
                    result = evaluator_mod.evaluate(program_path)
                finally:
                    os.chdir(orig_dir)

            if "error" in result:
                return self.fail(result["error"])

            combined_score = float(result.get("combined_score", 0.0))
            total_cost = result.get("total_cost", 0.0)
            successful = int(result.get("successful_configs", 0))

            explanation = (
                f"combined={combined_score:.6f} | "
                f"total_cost={total_cost:.2f} | "
                f"configs={successful}/5"
            )
            return self.score(combined_score, explanation)

        except Exception as e:
            return self.fail(f"Evaluation error: {e}")
