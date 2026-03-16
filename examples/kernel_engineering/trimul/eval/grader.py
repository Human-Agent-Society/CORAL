"""Kernel engineering grader for TriMul — runs Triton kernel benchmarks locally on GPU.

Wraps the eval harness to grade Triton kernel submissions on local GPU hardware.
"""

from __future__ import annotations

import logging
import math
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

import yaml

from coral.grader import TaskGrader
from coral.types import ScoreBundle

logger = logging.getLogger(__name__)


def _parse_popcorn_output(output: str) -> dict[str, str]:
    """Parse key-value pairs from the POPCORN_FD output."""
    results = {}
    for line in output.strip().splitlines():
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            results[key.strip()] = value.strip()
    return results


def _compute_geomean(values: list[float]) -> float:
    """Compute geometric mean of a list of values."""
    if not values:
        return 0.0
    log_sum = sum(math.log(v) for v in values if v > 0)
    return math.exp(log_sum / len(values))


class Grader(TaskGrader):
    """Grader for kernel engineering optimization tasks.

    Runs Triton kernel submissions through the eval harness on local GPU hardware.
    """

    def evaluate(self) -> ScoreBundle:
        task_name = self.args.get("task_name", "trimul")
        timeout = self.args.get("timeout", 1200)

        submission_path = os.path.join(self.codebase_path, "submission.py")
        if not os.path.exists(submission_path):
            return self.fail("submission.py not found in codebase")

        submission_code = Path(submission_path).read_text()
        if "custom_kernel" not in submission_code:
            return self.fail("submission.py must define a 'custom_kernel' function")

        # Load task config from eval/task.yml
        task_yml_path = self.read_eval_path("task.yml")
        with open(task_yml_path) as f:
            task_config = yaml.safe_load(f)

        ranking_by = task_config.get("ranking_by", "geom")
        test_timeout = task_config.get("test_timeout", timeout)
        ranked_timeout = task_config.get("ranked_timeout", timeout)

        # Run correctness tests first
        logger.info(f"Running correctness tests for {task_name}...")
        test_results = self._run_eval(
            submission_path, mode="test", timeout=test_timeout, ranking_by=ranking_by,
        )

        if test_results.get("check") != "pass":
            error = self._extract_test_errors(test_results)
            return self._make_result(
                correct=False, timing_us=None,
                feedback=f"Correctness check failed: {error}",
            )

        # Run leaderboard benchmarks
        logger.info(f"Running benchmarks for {task_name}...")
        bench_results = self._run_eval(
            submission_path, mode="leaderboard", timeout=ranked_timeout, ranking_by=ranking_by,
        )

        if bench_results.get("check") != "pass":
            error = self._extract_test_errors(bench_results)
            return self._make_result(
                correct=True, timing_us=None,
                feedback=f"Benchmark failed: {error}",
            )

        # Extract timing results
        timings = self._extract_timings(bench_results)
        if not timings:
            return self._make_result(
                correct=True, timing_us=None,
                feedback="Benchmarks passed but no timing data found",
            )

        # Aggregate timings
        if ranking_by == "last":
            agg_ns = timings[-1]
        elif ranking_by == "mean":
            agg_ns = sum(timings) / len(timings)
        else:  # "geom" (default)
            agg_ns = _compute_geomean(timings)

        agg_us = agg_ns / 1000.0

        return self._make_result(
            correct=True, timing_us=agg_us,
            feedback=f"Runtime ({ranking_by}): {agg_us:.2f} us across {len(timings)} benchmark(s)",
        )

    def _run_eval(
        self,
        submission_path: str,
        mode: str = "leaderboard",
        timeout: int = 1200,
        ranking_by: str = "geom",
    ) -> dict[str, str]:
        """Run the eval harness for a kernel engineering task."""
        eval_dir = Path(self.private_dir) / "eval"

        with tempfile.TemporaryDirectory(prefix="coral_kernel_") as tmpdir:
            # Copy harness files from eval/
            for f in eval_dir.iterdir():
                if f.name not in ("grader.py", "submission.py"):
                    if f.is_file():
                        shutil.copy2(f, tmpdir)

            # Copy agent's submission
            shutil.copy2(submission_path, os.path.join(tmpdir, "submission.py"))

            # Build test spec file from task.yml
            test_spec_path = os.path.join(tmpdir, f"{mode}.txt")
            self._write_test_specs(eval_dir / "task.yml", mode, test_spec_path, ranking_by)

            # Run eval.py with POPCORN_FD protocol
            read_fd, write_fd = os.pipe()

            env = os.environ.copy()
            env["POPCORN_FD"] = str(write_fd)

            cmd = ["/usr/bin/python3", "eval.py", mode, f"{mode}.txt"]
            logger.info(f"Running eval: {' '.join(cmd)} in {tmpdir}")

            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=tmpdir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    pass_fds=(write_fd,),
                )
                os.close(write_fd)
                write_fd = -1

                popcorn_output: list[str] = []

                def _read_popcorn():
                    with os.fdopen(read_fd, "r") as f:
                        popcorn_output.append(f.read())

                reader = threading.Thread(target=_read_popcorn, daemon=True)
                reader.start()

                stdout, stderr = proc.communicate(timeout=timeout)
                reader.join(timeout=10)

                if stderr:
                    logger.info(f"Eval stderr: {stderr.decode('utf-8', errors='replace')[:2000]}")

                return _parse_popcorn_output(popcorn_output[0] if popcorn_output else "")

            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                return {"check": "fail", "error": f"Eval timed out after {timeout}s"}
            except Exception as e:
                return {"check": "fail", "error": str(e)}
            finally:
                if write_fd >= 0:
                    try:
                        os.close(write_fd)
                    except OSError:
                        pass

    def _write_test_specs(
        self,
        task_yml_path: Path,
        mode: str,
        output_path: str,
        ranking_by: str = "geom",
    ) -> None:
        """Extract test specs from task.yml and write them for the eval harness."""
        with open(task_yml_path) as f:
            task_config = yaml.safe_load(f)

        if mode == "test":
            specs = task_config.get("tests", [])
        elif mode in ("benchmark", "leaderboard"):
            specs = task_config.get("benchmarks", [])
            if ranking_by == "last" and specs:
                specs = [specs[-1]]
        else:
            specs = task_config.get("tests", [])

        with open(output_path, "w") as f:
            for spec in specs:
                parts = [f"{k}: {v}" for k, v in spec.items()]
                f.write("; ".join(parts) + "\n")

    def _extract_timings(self, results: dict[str, str]) -> list[float]:
        """Extract mean timings from benchmark results."""
        timings = []
        count = int(results.get("benchmark-count", "0"))
        for i in range(count):
            mean_key = f"benchmark.{i}.mean"
            if mean_key in results:
                try:
                    timings.append(float(results[mean_key]))
                except ValueError:
                    continue
        return timings

    def _extract_test_errors(self, results: dict[str, str]) -> str:
        """Extract error messages from test results."""
        errors = []
        for key, value in results.items():
            if key.endswith(".error"):
                errors.append(value)
            elif key.endswith(".status") and value == "fail":
                idx = key.split(".")[1]
                spec = results.get(
                    f"test.{idx}.spec",
                    results.get(f"benchmark.{idx}.spec", ""),
                )
                errors.append(f"Failed on: {spec}")
        if errors:
            return "; ".join(errors[:3])
        return results.get("error", "Unknown error")

    def _make_result(
        self,
        correct: bool,
        timing_us: float | None,
        feedback: str,
    ) -> ScoreBundle:
        """Create a ScoreBundle from eval results.

        Score is: 1000 / timing_us (higher is better, lower time = higher score).
        If incorrect, score is 0.
        """
        if not correct or timing_us is None:
            return self.fail(feedback)

        score_value = 1000.0 / timing_us if timing_us > 0 else 0.0
        return self.score(score_value, feedback)
