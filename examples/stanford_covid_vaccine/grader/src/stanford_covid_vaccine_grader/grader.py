"""Stanford COVID Vaccine mRNA degradation prediction grader.

Evaluates programs that predict RNA degradation rates at each base position.
The program file must define a run(train_path, test_path) function returning
a DataFrame with columns: id_seqpos, reactivity, deg_Mg_pH10, deg_pH10,
deg_Mg_50C, deg_50C.

Grading uses MCRMSE (Mean Columnwise Root Mean Squared Error) over 3 scored
columns, matching the MLEBench/Kaggle implementation. Lower is better.
"""

from __future__ import annotations

import json
import os
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle


class Grader(TaskGrader):
    """Grader for the Stanford COVID Vaccine degradation prediction task."""

    def evaluate(self) -> ScoreBundle:
        program_file = self.args.get("program_file", "solution.py")
        train_file = self.args.get("train_file", "data/train.json")
        test_file = self.args.get("test_file", "data/test.json")
        timeout = self.timeout

        program_path = os.path.join(self.codebase_path, program_file)
        train_path = os.path.join(self.codebase_path, train_file)
        test_path = os.path.join(self.codebase_path, test_file)
        answers_path = str(self.read_eval_path("answers/test.csv"))

        # Check required files exist
        for path, label in [
            (program_path, f"Program file ({program_file})"),
            (train_path, f"Training data ({train_file})"),
            (test_path, f"Test data ({test_file})"),
            (answers_path, "Answer key (eval/answers/test.csv)"),
        ]:
            if not os.path.exists(path):
                return self.fail(f"{label} not found")

        try:
            result = _run_evaluation(program_path, train_path, test_path, answers_path, timeout, self.get_python_command())
        except TimeoutError:
            return self.fail(f"Evaluation timed out after {timeout}s")
        except Exception as e:
            return self.fail(f"Evaluation failed: {e}")

        if "error" in result:
            return self.fail(f"Error: {result['error']}")

        mcrmse = result["mcrmse"]
        per_col = result.get("per_column", {})
        eval_time = result.get("eval_time", 0.0)

        col_details = ", ".join(f"{k}: {v:.5f}" for k, v in per_col.items())
        explanation = (
            f"MCRMSE: {mcrmse:.5f} ({col_details}) | "
            f"Time: {eval_time:.1f}s"
        )

        return self.score(mcrmse, explanation)


def _run_evaluation(
    program_path: str,
    train_path: str,
    test_path: str,
    answers_path: str,
    timeout: int,
    python_cmd: list[str],
) -> dict:
    """Run the solution in a subprocess and grade against answer key."""
    import subprocess

    script = textwrap.dedent(f"""\
        import json, sys, os, time
        import numpy as np
        import pandas as pd
        from sklearn.metrics import root_mean_squared_error

        sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
        module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
        program = __import__(module_name)

        train_path = {train_path!r}
        test_path = {test_path!r}
        answers_path = {answers_path!r}

        start = time.time()
        submission = program.run(train_path, test_path)
        eval_time = time.time() - start

        if not isinstance(submission, pd.DataFrame):
            raise ValueError(f"run() must return a DataFrame, got {{type(submission).__name__}}")

        # Validate required columns
        required_cols = ["id_seqpos", "reactivity", "deg_Mg_pH10", "deg_pH10", "deg_Mg_50C", "deg_50C"]
        missing = [c for c in required_cols if c not in submission.columns]
        if missing:
            raise ValueError(f"Submission missing columns: {{missing}}")

        answers = pd.read_csv(answers_path)

        if len(submission) != len(answers):
            raise ValueError(
                f"Submission has {{len(submission)}} rows, expected {{len(answers)}}"
            )

        # Sort by id_seqpos for consistent comparison
        submission = submission.sort_values("id_seqpos").reset_index(drop=True)
        answers = answers.sort_values("id_seqpos").reset_index(drop=True)

        # Verify id_seqpos match
        if (submission["id_seqpos"].values != answers["id_seqpos"].values).any():
            raise ValueError("id_seqpos values in submission do not match answer key")

        # Apply keep mask — only score first seq_scored positions per sequence
        mask = answers["keep"]
        scored_submission = submission[mask]
        scored_answers = answers[mask]

        # Compute MCRMSE over 3 scored columns
        scored_cols = ["reactivity", "deg_Mg_pH10", "deg_Mg_50C"]
        per_column = {{}}
        errors = []
        for col in scored_cols:
            y_pred = scored_submission[col].values.astype(float)
            y_true = scored_answers[col].values.astype(float)
            rmse = root_mean_squared_error(y_true=y_true, y_pred=y_pred)
            per_column[col] = round(float(rmse), 5)
            errors.append(rmse)

        mcrmse = float(np.mean(errors))

        print(json.dumps({{
            "mcrmse": round(mcrmse, 5),
            "per_column": per_column,
            "eval_time": eval_time,
        }}))
    """)
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
