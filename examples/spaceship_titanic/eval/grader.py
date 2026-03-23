"""Spaceship Titanic classification grader.

Evaluates programs that predict which passengers were transported to an
alternate dimension. The program file must define a run(train_path, test_path)
function returning a DataFrame with PassengerId and Transported columns.

Grading uses sklearn.metrics.accuracy_score, matching the mlebench implementation.
"""

from __future__ import annotations

import json
import os
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle


class Grader(TaskGrader):
    """Grader for the Spaceship Titanic classification task."""

    def evaluate(self) -> ScoreBundle:
        program_file = self.args.get("program_file", "solution.py")
        train_file = self.args.get("train_file", "data/train.csv")
        test_file = self.args.get("test_file", "data/test.csv")
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

        accuracy = result["accuracy"]
        n_correct = result["n_correct"]
        n_total = result["n_total"]
        eval_time = result.get("eval_time", 0.0)

        explanation = (
            f"Accuracy: {accuracy:.5f} ({n_correct}/{n_total} correct) | "
            f"Time: {eval_time:.1f}s"
        )

        return self.score(accuracy, explanation)


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
        import pandas as pd
        from sklearn.metrics import accuracy_score

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
        if "PassengerId" not in submission.columns:
            raise ValueError("Submission must have a PassengerId column")
        if "Transported" not in submission.columns:
            raise ValueError("Submission must have a Transported column")

        answers = pd.read_csv(answers_path)
        if len(submission) != len(answers):
            raise ValueError(
                f"Submission has {{len(submission)}} rows, expected {{len(answers)}}"
            )

        submission = submission.sort_values("PassengerId").reset_index(drop=True)
        answers = answers.sort_values("PassengerId").reset_index(drop=True)

        if (submission["PassengerId"].values != answers["PassengerId"].values).any():
            raise ValueError("PassengerIds in submission do not match answer key")

        y_true = answers["Transported"].to_numpy()
        y_pred = submission["Transported"].to_numpy()
        acc = float(accuracy_score(y_true=y_true, y_pred=y_pred))
        n_correct = int((y_true == y_pred).sum())
        n_total = len(answers)

        print(json.dumps({{
            "accuracy": round(acc, 5),
            "n_correct": n_correct,
            "n_total": n_total,
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
