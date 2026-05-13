"""Pfly 4-class peptide detectability grader.

Evaluates programs that predict the detectability class (0=Non-Flyer,
1=Weak, 2=Intermediate, 3=Strong) for each peptide sequence in
``data/test.parquet``. Hidden test labels ship inside this package and are
loaded via ``importlib.resources``.

The agent's ``run()`` may return either:

* A ``(N, 4)`` float array of softmax probabilities (rows sum to 1.0).
  Preferred — unlocks per-class AUC and binary AUC in feedback.
* A ``(N,)`` int64 array of hard class predictions in ``{0, 1, 2, 3}``.
  Still scored on accuracy and the rest; AUC fields read ``N/A``.

Reported metric set mirrors Abdul-Khalek et al., J. Proteome Res. 2025
("To Fly, or Not to Fly..."), §3.1 base-model evaluation on ProteomeTools:

  4-class:
    - Categorical accuracy                 (paper: 0.66)
    - Per-class AUC (one-vs-rest)          (paper: 0.97 / 0.85 / 0.78 / 0.90)
    - Neighbor-class misclassification     (paper: ~87% of errors)

  Binary (flyer vs non-flyer):
    - Accuracy, MCC, Precision, Recall, F1, AUC
                                           (paper: 0.94 / 0.85 / 0.96 / 0.97 / 0.96 / 0.97)

The score returned to the daemon is 4-class categorical accuracy
(direction = maximize), matching the optimization target the paper
benchmarks against.
"""
from __future__ import annotations

import fcntl
import importlib.resources
import json
import os
import textwrap
import time
from pathlib import Path

from coral.grader import TaskGrader
from coral.types import ScoreBundle


CLASS_NAMES = {
    0: "Non-Flyer",
    1: "Weak Flyer",
    2: "Intermediate Flyer",
    3: "Strong Flyer",
}

# Cross-process GPU lock directory. flock() releases automatically on fd close
# (or process exit), so stale locks from crashed graders self-heal. Shared
# across all CORAL runs on the same host — two runs targeting overlapping GPU
# pools will correctly serialize.
_GPU_LOCK_DIR = Path("/tmp/coral_gpu_locks")


def _acquire_gpu(
    pool: list[int],
    wait_timeout: float = 3600.0,
    poll_interval: float = 0.25,
) -> tuple[int, int]:
    """Acquire an exclusive flock on one GPU from ``pool``.

    Returns ``(gpu_id, fd)``. Caller MUST ``os.close(fd)`` to release the lock.
    Iterates the pool in order, picking the first GPU whose lockfile is free.
    Blocks up to ``wait_timeout`` seconds before raising ``TimeoutError``.
    """
    _GPU_LOCK_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + wait_timeout
    while True:
        for gpu in pool:
            lock_path = _GPU_LOCK_DIR / f"gpu_{gpu}.lock"
            fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return gpu, fd
            except BlockingIOError:
                os.close(fd)
        if time.time() >= deadline:
            raise TimeoutError(f"No GPU from {pool} free within {wait_timeout}s")
        time.sleep(poll_interval)


class Grader(TaskGrader):
    """Grader for the Pfly 4-class detectability task."""

    def evaluate(self) -> ScoreBundle:
        program_file = self.args.get("program_file", "solution.py")
        train_file = self.args.get("train_file", "data/train.parquet")
        val_file = self.args.get("val_file", "data/val.parquet")
        test_file = self.args.get("test_file", "data/test.parquet")
        timeout = self.timeout

        # Optional GPU pinning. When set, each eval acquires an exclusive lock
        # on one GPU from the pool and runs with CUDA_VISIBLE_DEVICES=<id> so
        # the agent's solution.py just sees a single cuda:0 device. Combine
        # with grader.parallel.max_workers <= len(gpu_pool) to grade in parallel
        # without the workers piling onto the same GPU.
        gpu_pool_raw = self.args.get("gpu_pool")
        gpu_pool: list[int] | None = None
        if gpu_pool_raw:
            try:
                gpu_pool = [int(g) for g in gpu_pool_raw]
            except (TypeError, ValueError):
                return self.fail(
                    f"grader.args.gpu_pool must be a list of int GPU indices, "
                    f"got {gpu_pool_raw!r}"
                )

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
                gpu_pool=gpu_pool,
            )
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
        per_class_auc = result.get("per_class_auc")        # dict[str,float] or None
        neighbor_rate = result.get("neighbor_error_rate")  # float or None
        n_errors = result.get("n_errors", 0)
        bin_acc = result["binary_accuracy"]
        bin_mcc = result["binary_mcc"]
        bin_prec = result["binary_precision"]
        bin_rec = result["binary_recall"]
        bin_f1 = result["binary_f1"]
        bin_auc = result.get("binary_auc")                 # float or None
        return_kind = result.get("return_kind", "labels")  # "probs" or "labels"
        gpu_id = result.get("gpu_id")                      # int or None

        def _fmt(x: float | None) -> str:
            return "N/A" if x is None else f"{x:.4f}"

        # Single-line explanation (shown in leaderboard).
        explanation_parts = [
            f"Acc: {accuracy:.4f}",
            f"Bin-Acc: {bin_acc:.4f}",
            f"Bin-MCC: {bin_mcc:.4f}",
        ]
        if bin_auc is not None:
            explanation_parts.append(f"Bin-AUC: {bin_auc:.4f}")
        explanation_parts.append(f"({n_correct}/{n_total})")
        explanation_parts.append(f"Time: {eval_time:.1f}s")
        explanation = " | ".join(explanation_parts)

        # Multi-line feedback mirrors the Pfly paper's reporting layout.
        feedback_lines = [
            "4-class (categorical):",
            f"  Accuracy:                       {accuracy:.4f}  ({n_correct}/{n_total})",
            "  Per-class AUC (one-vs-rest):",
        ]
        for c in range(4):
            auc_val = (per_class_auc or {}).get(str(c))
            feedback_lines.append(
                f"    {c} {CLASS_NAMES[c]:<20s} AUC = {_fmt(auc_val)}"
            )
        if n_errors > 0 and neighbor_rate is not None:
            feedback_lines.append(
                f"  Neighbor-class errors:          {neighbor_rate:.1%}  "
                f"(fraction of {n_errors} mistakes that landed in an adjacent class; paper ~87%)"
            )
        else:
            feedback_lines.append("  Neighbor-class errors:          N/A (no misclassifications)")
        feedback_lines.extend([
            "",
            "Binary (flyer vs non-flyer; class 0 vs classes 1-3):",
            f"  Accuracy:  {bin_acc:.4f}",
            f"  MCC:       {bin_mcc:.4f}",
            f"  Precision: {bin_prec:.4f}",
            f"  Recall:    {bin_rec:.4f}",
            f"  F1:        {bin_f1:.4f}",
            f"  AUC:       {_fmt(bin_auc)}",
            "",
            f"Eval time: {eval_time:.1f}s"
            + (f"  (CUDA_VISIBLE_DEVICES={gpu_id})" if gpu_id is not None else ""),
        ])
        if return_kind != "probs":
            feedback_lines.append(
                "Note: run() returned hard labels — return a (N, 4) probability "
                "matrix to unlock the per-class AUC and binary AUC fields."
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
    gpu_pool: list[int] | None = None,
) -> dict:
    import subprocess

    env = os.environ.copy()
    gpu_fd: int | None = None
    gpu_id: int | None = None
    if gpu_pool:
        # Wait up to ~1 hour for a GPU to free up. With max_workers <= len(pool)
        # this is effectively instant; the timeout just guards against deadlock.
        gpu_id, gpu_fd = _acquire_gpu(gpu_pool, wait_timeout=3600.0)
        env["CUDA_VISIBLE_DEVICES"] = str(gpu_id)

    script = textwrap.dedent(f"""\
        import json, sys, os, time
        import numpy as np
        import pandas as pd
        from sklearn.metrics import (
            accuracy_score, precision_score, recall_score, f1_score,
            matthews_corrcoef, roc_auc_score,
        )

        sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
        module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
        program = __import__(module_name)

        train_path = {train_path!r}
        val_path = {val_path!r}
        test_path = {test_path!r}
        labels_path = {labels_path!r}

        start = time.time()
        raw = program.run(train_path, val_path, test_path)
        eval_time = time.time() - start

        raw = np.asarray(raw)
        y_true = pd.read_parquet(labels_path)["label"].to_numpy(dtype=int)
        n_total = int(len(y_true))

        # Accept either (N, 4) probabilities or (N,) hard labels.
        probs = None
        if raw.ndim == 2 and raw.shape == (n_total, 4):
            probs = raw.astype(np.float64)
            row_sums = probs.sum(axis=1)
            if not np.allclose(row_sums, 1.0, atol=1e-3):
                # numerically stable softmax fallback if rows don't normalize
                shifted = probs - probs.max(axis=1, keepdims=True)
                exp = np.exp(shifted)
                probs = exp / exp.sum(axis=1, keepdims=True)
            predictions = probs.argmax(axis=1).astype(int)
            return_kind = "probs"
        elif raw.ndim == 1 and raw.shape == (n_total,):
            predictions = raw.astype(int).ravel()
            return_kind = "labels"
        else:
            raise ValueError(
                f"Unexpected return shape {{raw.shape}}: expected ({{n_total}},) "
                f"int labels OR ({{n_total}}, 4) float probabilities."
            )

        if predictions.size and (predictions.min() < 0 or predictions.max() > 3):
            raise ValueError(
                f"Predictions must be in [0, 3]; got "
                f"[{{predictions.min()}}, {{predictions.max()}}]"
            )

        # ----- 4-class metrics (paper §3.1) -----
        acc = float(accuracy_score(y_true=y_true, y_pred=predictions))

        per_class_auc = None
        if probs is not None:
            aucs = []
            for c in range(4):
                aucs.append(float(roc_auc_score((y_true == c).astype(int), probs[:, c])))
            per_class_auc = {{str(i): round(aucs[i], 5) for i in range(4)}}

        # Neighbor-class error rate: of MISCLASSIFIED examples, fraction with
        # |true - pred| == 1 (adjacent in the ordered class scale). Paper ~87%.
        errors_mask = predictions != y_true
        n_errors = int(errors_mask.sum())
        neighbor_rate = None
        if n_errors > 0:
            adj = (np.abs(predictions[errors_mask] - y_true[errors_mask]) == 1).sum()
            neighbor_rate = round(float(adj) / float(n_errors), 5)

        # ----- Binary (flyer vs non-flyer) -----
        y_true_bin = (y_true > 0).astype(int)
        pred_bin = (predictions > 0).astype(int)
        bin_acc = float(accuracy_score(y_true=y_true_bin, y_pred=pred_bin))
        bin_mcc = float(matthews_corrcoef(y_true_bin, pred_bin))
        bin_prec = float(precision_score(y_true=y_true_bin, y_pred=pred_bin, zero_division=0))
        bin_rec = float(recall_score(y_true=y_true_bin, y_pred=pred_bin, zero_division=0))
        bin_f1 = float(f1_score(y_true=y_true_bin, y_pred=pred_bin, zero_division=0))
        bin_auc = None
        if probs is not None:
            flyer_prob = 1.0 - probs[:, 0]
            bin_auc = round(float(roc_auc_score(y_true=y_true_bin, y_score=flyer_prob)), 5)

        n_correct = int((y_true == predictions).sum())

        print(json.dumps({{
            "accuracy": round(acc, 5),
            "per_class_auc": per_class_auc,
            "neighbor_error_rate": neighbor_rate,
            "n_errors": n_errors,
            "binary_accuracy": round(bin_acc, 5),
            "binary_mcc": round(bin_mcc, 5),
            "binary_precision": round(bin_prec, 5),
            "binary_recall": round(bin_rec, 5),
            "binary_f1": round(bin_f1, 5),
            "binary_auc": bin_auc,
            "n_correct": n_correct,
            "n_total": n_total,
            "eval_time": round(eval_time, 2),
            "return_kind": return_kind,
        }}))
    """)
    try:
        result = subprocess.run(
            [*python_cmd, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    finally:
        # Release the GPU lock as soon as the subprocess exits, success or not.
        # flock is also released on fd close, so this is belt-and-suspenders.
        if gpu_fd is not None:
            os.close(gpu_fd)

    def _attach_gpu(d: dict) -> dict:
        if gpu_id is not None:
            d["gpu_id"] = gpu_id
        return d

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-2000:])
    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(
            f"Script produced no output.\nstderr: {result.stderr.strip()[-1000:]}"
        )
    try:
        return _attach_gpu(json.loads(stdout))
    except json.JSONDecodeError:
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return _attach_gpu(json.loads(line))
                except json.JSONDecodeError:
                    continue
        raise RuntimeError(
            f"No valid JSON in output.\nstdout: {stdout[-500:]}\nstderr: {result.stderr.strip()[-500:]}"
        )
