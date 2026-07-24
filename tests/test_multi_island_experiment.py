"""Integrity checks for the multi-island experiment tooling."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from examples.kernel_builder.grader.src.kernel_builder_grader import grader as kernel_grader
from experiments.multi_island import analyze, run_matrix


def _write_attempt(
    run_dir: Path,
    commit_hash: str,
    *,
    budget_class: str,
    score: float | None,
    feedback: str = "",
) -> None:
    attempts = run_dir / ".coral" / "public" / "attempts"
    attempts.mkdir(parents=True, exist_ok=True)
    (attempts / f"{commit_hash}.json").write_text(
        json.dumps(
            {
                "commit_hash": commit_hash,
                "status": "crashed" if score is None else "improved",
                "score": score,
                "feedback": feedback,
                "metadata": {"budget_class": budget_class},
            }
        )
    )


def test_rejected_tune_is_recorded_without_invalidating_run(tmp_path: Path) -> None:
    _write_attempt(
        tmp_path,
        "rejected-tune",
        budget_class="tune",
        score=None,
        feedback=f"eval: {run_matrix.TUNE_DISABLED_MARKER}; submit an ordinary coral eval.",
    )

    records, grader_errors, tune_attempts, tune_violations = analyze.attempt_records(tmp_path)

    assert records == []
    assert grader_errors == 0
    assert tune_attempts == 1
    assert tune_violations == 0
    assert run_matrix.disallowed_attempts(tmp_path) == []


def test_grader_error_and_unguarded_tune_invalidate_run(tmp_path: Path) -> None:
    _write_attempt(
        tmp_path,
        "grader-error",
        budget_class="grader_error",
        score=None,
        feedback="Eval timed out after 120s.",
    )
    _write_attempt(
        tmp_path,
        "scored-tune",
        budget_class="tune",
        score=123.0,
        feedback="Tune score: 123",
    )

    records, grader_errors, tune_attempts, tune_violations = analyze.attempt_records(tmp_path)

    assert records == []
    assert grader_errors == 1
    assert tune_attempts == 1
    assert tune_violations == 1
    assert {record["commit_hash"] for record in run_matrix.disallowed_attempts(tmp_path)} == {
        "grader-error",
        "scored-tune",
    }


def test_kernel_candidate_timeout_becomes_task_level_failure(monkeypatch) -> None:
    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=kwargs.get("args", "python"), timeout=120)

    monkeypatch.setattr(kernel_grader.subprocess, "run", raise_timeout)

    with pytest.raises(TimeoutError):
        kernel_grader._run_evaluation(
            "candidate.py",
            "frozen_problem.py",
            120,
            ["python"],
            kernel_grader.REAL_PARAMS,
        )


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="bubblewrap is not installed")
def test_hardened_kernel_builder_cannot_exfiltrate_private_files(tmp_path: Path) -> None:
    private_marker = tmp_path / "private-marker.txt"
    leak_path = tmp_path / "leaked.txt"
    private_marker.write_text("hidden simulator material")
    seed_path = Path("examples/kernel_builder/seed/kernel_builder.py")
    candidate_path = tmp_path / "kernel_builder.py"
    candidate_path.write_text(
        "from pathlib import Path\n"
        "try:\n"
        f"    secret = Path({str(private_marker)!r}).read_text()\n"
        f"    Path({str(leak_path)!r}).write_text(secret)\n"
        "except Exception:\n"
        "    pass\n\n"
        "try:\n"
        "    import frozen_problem\n"
        f"    Path({str(leak_path)!r}).write_text(frozen_problem.__file__)\n"
        "except Exception:\n"
        "    pass\n\n"
        + seed_path.read_text()
    )

    result = kernel_grader._run_hardened_evaluation(
        str(candidate_path),
        "examples/kernel_builder/taskdata/frozen_problem.py",
        120,
        [sys.executable],
        {**kernel_grader.REAL_PARAMS, "iterations": 1},
    )

    assert result["is_correct"] is True
    assert not leak_path.exists()
