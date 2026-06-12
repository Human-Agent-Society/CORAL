"""MNIST digit classification grader.

Evaluates programs that classify 28x28 handwritten digit images (0-9).
The program file must define a run(train_path, test_path) function returning
a numpy int array of shape (10000,) with predicted digit labels.

Grading uses sklearn.metrics.accuracy_score against held-out test labels.
"""

from __future__ import annotations

import json
import os
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle


class Grader(TaskGrader):
    """Grader for the MNIST digit classification task."""

    def evaluate(self) -> ScoreBundle:
        program_file = self.args.get("program_file", "solution.py")
        train_file = self.args.get("train_file", "data/train.npz")
        test_file = self.args.get("test_file", "data/test.npz")
        timeout = self.timeout

        program_path = os.path.join(self.codebase_path, program_file)
        train_path = os.path.join(self.codebase_path, train_file)
        test_path = os.path.join(self.codebase_path, test_file)
        answers_path = str(self.read_eval_path("answers/test_labels.npz"))

        for path, label in [
            (program_path, f"Program file ({program_file})"),
            (train_path, f"Training data ({train_file})"),
            (test_path, f"Test data ({test_file})"),
            (answers_path, "Answer key (eval/answers/test_labels.npz)"),
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
        per_digit = result.get("per_digit", {})

        explanation = (
            f"Accuracy: {accuracy:.5f} ({n_correct}/{n_total} correct) | "
            f"Time: {eval_time:.1f}s"
        )
        if per_digit:
            worst = min(per_digit.items(), key=lambda x: x[1])
            best = max(per_digit.items(), key=lambda x: x[1])
            explanation += f" | Best digit: {best[0]} ({best[1]:.3f}), Worst: {worst[0]} ({worst[1]:.3f})"

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
        import numpy as np
        from sklearn.metrics import accuracy_score

        sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
        module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
        program = __import__(module_name)

        train_path = {train_path!r}
        test_path = {test_path!r}
        answers_path = {answers_path!r}

        start = time.time()
        predictions = program.run(train_path, test_path)
        eval_time = time.time() - start

        predictions = np.asarray(predictions, dtype=int)
        y_true = np.load(answers_path)["labels"]

        if predictions.shape != y_true.shape:
            raise ValueError(
                f"Predictions shape {{predictions.shape}} != expected {{y_true.shape}}"
            )

        acc = float(accuracy_score(y_true=y_true, y_pred=predictions))
        n_correct = int((y_true == predictions).sum())
        n_total = len(y_true)

        # Per-digit accuracy
        per_digit = {{}}
        for d in range(10):
            mask = y_true == d
            if mask.sum() > 0:
                per_digit[str(d)] = float((predictions[mask] == d).sum() / mask.sum())

        print(json.dumps({{
            "accuracy": round(acc, 5),
            "n_correct": n_correct,
            "n_total": n_total,
            "eval_time": eval_time,
            "per_digit": per_digit,
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
