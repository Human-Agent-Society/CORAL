"""Pfly 4-class peptide detectability grader.

Evaluates programs that predict the detectability class (0=Non-Flyer,
1=Weak, 2=Intermediate, 3=Strong) for each peptide sequence in
``data/test.parquet``. Hidden test labels ship inside this package and are
loaded via ``importlib.resources``.
"""
from __future__ import annotations

import importlib.resources
import json
import os
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle


CLASS_NAMES = {
    0: "Non-Flyer",
    1: "Weak Flyer",
    2: "Intermediate Flyer",
    3: "Strong Flyer",
}


class Grader(TaskGrader):
    """Grader for the Pfly 4-class detectability task."""

    def evaluate(self) -> ScoreBundle:
        program_file = self.args.get("program_file", "solution.py")
        train_file = self.args.get("train_file", "data/train.parquet")
        val_file = self.args.get("val_file", "data/val.parquet")
        test_file = self.args.get("test_file", "data/test.parquet")
        timeout = self.timeout

        program_path = os.path.join(self.codebase_path, program_file)
        train_path = os.path.join(self.codebase_path, train_file)
        val_path = os.path.join(self.codebase_path, val_file)
        test_path = os.path.join(self.codebase_path, test_file)
        labels_path = str(
            importlib.resources.files("dlomix_pfly_grader.data") / "test_labels.parquet"
        )

        for path, label in [
            (program_path, f"Program file ({program_file})"),
            (train_path, f"Training data ({train_file})"),
            (val_path, f"Validation data ({val_file})"),
            (test_path, f"Test data ({test_file})"),
            (labels_path, "Hidden test labels"),
        ]:
            if not os.path.exists(path):
                return self.fail(f"{label} not found at {path}")

        try:
            result = _run_evaluation(
                program_path, train_path, val_path, test_path, labels_path,
                timeout, self.get_python_command(),
            )
        except TimeoutError:
            return self.fail(f"Evaluation timed out after {timeout}s")
        except Exception as e:
            return self.fail(f"Evaluation failed: {e}")

        if "error" in result:
            return self.fail(f"Error: {result['error']}")

        accuracy = result["accuracy"]
        macro_f1 = result["macro_f1"]
        n_correct = result["n_correct"]
        n_total = result["n_total"]
        eval_time = result.get("eval_time", 0.0)
        per_class_f1 = result.get("per_class_f1", {})

        explanation = (
            f"Accuracy: {accuracy:.4f} | Macro-F1: {macro_f1:.4f} "
            f"({n_correct}/{n_total}) | Time: {eval_time:.1f}s"
        )

        feedback_lines = [
            f"Accuracy:  {accuracy:.4f}  ({n_correct}/{n_total})",
            f"Macro-F1:  {macro_f1:.4f}",
            f"Eval time: {eval_time:.1f}s",
            "Per-class F1:",
        ]
        for k in sorted(per_class_f1.keys(), key=int):
            feedback_lines.append(
                f"  {int(k)} {CLASS_NAMES.get(int(k), '?'):<20s} F1 = {per_class_f1[k]:.4f}"
            )
        return self.score(accuracy, explanation, feedback="\n".join(feedback_lines))


def _run_evaluation(
    program_path: str,
    train_path: str,
    val_path: str,
    test_path: str,
    labels_path: str,
    timeout: int,
    python_cmd: list[str],
) -> dict:
    import subprocess

    script = textwrap.dedent(f"""\
        import json, sys, os, time
        import numpy as np
        import pandas as pd
        from sklearn.metrics import accuracy_score, f1_score

        sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
        module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
        program = __import__(module_name)

        train_path = {train_path!r}
        val_path = {val_path!r}
        test_path = {test_path!r}
        labels_path = {labels_path!r}

        start = time.time()
        predictions = program.run(train_path, val_path, test_path)
        eval_time = time.time() - start

        predictions = np.asarray(predictions, dtype=int).ravel()
        y_true = pd.read_parquet(labels_path)["label"].to_numpy(dtype=int)

        if predictions.shape != y_true.shape:
            raise ValueError(
                f"Predictions shape {{predictions.shape}} != expected {{y_true.shape}}"
            )
        if predictions.size and (predictions.min() < 0 or predictions.max() > 3):
            raise ValueError(
                f"Predictions must be in [0, 3]; got [{{predictions.min()}}, {{predictions.max()}}]"
            )

        acc = float(accuracy_score(y_true=y_true, y_pred=predictions))
        macro = float(f1_score(y_true=y_true, y_pred=predictions, average="macro"))
        per_class = f1_score(y_true=y_true, y_pred=predictions, average=None, labels=[0, 1, 2, 3])

        n_correct = int((y_true == predictions).sum())
        n_total = int(len(y_true))

        print(json.dumps({{
            "accuracy": round(acc, 5),
            "macro_f1": round(macro, 5),
            "per_class_f1": {{str(i): round(float(per_class[i]), 5) for i in range(4)}},
            "n_correct": n_correct,
            "n_total": n_total,
            "eval_time": round(eval_time, 2),
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
