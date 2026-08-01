"""Local, private-data evaluator for Frontier-CS algorithmic problem #0.

The upstream ``frontier_cs`` Python package does not ship its ``algorithmic/``
checkout, and its normal evaluator requires a privileged Docker go-judge
service.  The scaling experiment therefore uses the same released checker
and test cases through a small local runner.  The checkout lives below
``TaskGrader.private_dir`` and is never visible in an agent worktree.
"""

from __future__ import annotations

import fcntl
import math
import os
import re
import signal
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from coral.grader import TaskGrader
from coral.types import ScoreBundle

from .constants import checkout_path

RATIO_RE = re.compile(r"Ratio:\s*([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)")


def _run_limited(
    command: list[str],
    *,
    stdin_path: Path | None = None,
    stdout_path: Path | None = None,
    timeout: float,
) -> tuple[int | None, str, bool]:
    """Run one case and kill its process group on a wall-clock timeout."""

    stdin = stdin_path.open("rb") if stdin_path else subprocess.DEVNULL
    stdout = stdout_path.open("wb") if stdout_path else subprocess.PIPE
    try:
        process = subprocess.Popen(
            command,
            stdin=stdin,
            stdout=stdout,
            stderr=subprocess.PIPE,
            start_new_session=True,
            text=False,
        )
        try:
            captured_stdout, stderr = process.communicate(timeout=timeout)
            captured = (captured_stdout or b"") + (stderr or b"")
            return process.returncode, captured.decode(errors="replace"), False
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            captured_stdout, stderr = process.communicate()
            captured = (captured_stdout or b"") + (stderr or b"")
            return process.returncode, captured.decode(errors="replace"), True
    finally:
        if stdin is not subprocess.DEVNULL:
            stdin.close()
        if stdout is not subprocess.PIPE:
            stdout.close()


class Grader(TaskGrader):
    """Score all released public cases for Pack the Polyominoes."""

    def _problem_dir(self) -> Path:
        problem_id = str(self.args.get("problem_id", "0"))
        return checkout_path(self.private_dir) / "algorithmic" / "problems" / problem_id

    def _checker_binary(self, problem_dir: Path, scratch: Path) -> Path:
        cache_dir = Path(self.private_dir) / "scaling-poly-checkers"
        cache_dir.mkdir(parents=True, exist_ok=True)
        checker = cache_dir / f"{problem_dir.name}.bin"
        lock_path = cache_dir / f"{problem_dir.name}.lock"
        with lock_path.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not checker.exists():
                candidate = scratch / "checker.bin"
                result = subprocess.run(
                    [
                        "g++",
                        str(problem_dir / "chk.cc"),
                        "-O2",
                        "-pipe",
                        "-std=gnu++17",
                        "-I",
                        str(checkout_path(self.private_dir) / "algorithmic" / "judge" / "include"),
                        "-o",
                        str(candidate),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode != 0:
                    raise RuntimeError("checker compilation failed: " + result.stderr[-2000:])
                os.replace(candidate, checker)
            fcntl.flock(lock, fcntl.LOCK_UN)
        return checker

    @staticmethod
    def _cases(problem_dir: Path) -> list[tuple[Path, Path]]:
        testdata = problem_dir / "testdata"
        cases = []
        for input_path in testdata.glob("*.in"):
            answer_path = input_path.with_suffix(".ans")
            if answer_path.exists():
                cases.append((input_path, answer_path))
        return sorted(cases, key=lambda pair: int(pair[0].stem))

    def _score_case(
        self,
        *,
        candidate: Path,
        checker: Path,
        input_path: Path,
        answer_path: Path,
        output_path: Path,
        time_limit: float,
        memory_mb: int,
    ) -> tuple[float, str]:
        candidate_command = [
            "prlimit",
            f"--as={memory_mb * 1024 * 1024}",
            "--fsize=134217728",
            f"--cpu={max(1, math.ceil(time_limit))}",
            "--",
            str(candidate),
        ]
        returncode, stderr, timed_out = _run_limited(
            candidate_command,
            stdin_path=input_path,
            stdout_path=output_path,
            timeout=max(4.0, time_limit * 2.25),
        )
        if timed_out:
            return 0.0, "candidate timed out"
        if returncode != 0:
            return 0.0, f"candidate exited {returncode}: {stderr[-240:]}"

        checker_command = [
            "prlimit",
            "--as=268435456",
            "--fsize=8388608",
            "--cpu=10",
            "--",
            str(checker),
            str(input_path),
            str(output_path),
            str(answer_path),
        ]
        check_returncode, check_stderr, check_timed_out = _run_limited(
            checker_command,
            timeout=20.0,
        )
        if check_timed_out:
            return 0.0, "checker timed out"
        feedback = check_stderr
        ratio_match = RATIO_RE.search(feedback)
        if ratio_match is None:
            return 0.0, f"checker exited {check_returncode}: {feedback[-240:]}"
        ratio = float(ratio_match.group(1))
        if not 0.0 <= ratio <= 1.0:
            return 0.0, f"checker returned invalid ratio {ratio}"
        return ratio, ""

    def evaluate(self) -> ScoreBundle:
        problem_dir = self._problem_dir()
        if not problem_dir.is_dir():
            raise RuntimeError(f"private Frontier-CS problem data not found: {problem_dir}")
        solution_path = Path(self.codebase_path) / "solution.cpp"
        if not solution_path.exists():
            return self.score(0.0, feedback="No solution.cpp found in workspace.")

        cases = self._cases(problem_dir)
        if not cases:
            raise RuntimeError(f"no public test cases found under {problem_dir}")
        time_limit = float(self.args.get("time_limit", 2))
        memory_mb = int(self.args.get("memory_mb", 256))
        with tempfile.TemporaryDirectory(prefix="poly-eval-", dir=self.private_dir) as temp:
            scratch = Path(temp)
            candidate = scratch / "solution"
            compile_result = subprocess.run(
                ["g++", str(solution_path), "-O2", "-pipe", "-std=c++17", "-o", str(candidate)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if compile_result.returncode != 0:
                return self.score(
                    0.0,
                    feedback=f"Candidate build failed: {compile_result.stderr[-2000:]}",
                )
            checker = self._checker_binary(problem_dir, scratch)
            case_dir = scratch / "outputs"
            case_dir.mkdir()
            jobs: list[dict[str, Any]] = []
            with ThreadPoolExecutor(max_workers=min(4, len(cases))) as pool:
                futures = [
                    pool.submit(
                        self._score_case,
                        candidate=candidate,
                        checker=checker,
                        input_path=input_path,
                        answer_path=answer_path,
                        output_path=case_dir / f"case-{index:03d}.out",
                        time_limit=time_limit,
                        memory_mb=memory_mb,
                    )
                    for index, (input_path, answer_path) in enumerate(cases, 1)
                ]
                for index, future in enumerate(futures, 1):
                    ratio, detail = future.result()
                    jobs.append({"case": index, "ratio": ratio, "detail": detail})

        total_ratio = sum(item["ratio"] for item in jobs) / len(jobs)
        score = total_ratio * 100.0
        valid = sum(item["ratio"] > 0 for item in jobs)
        details = next((item["detail"] for item in jobs if item["detail"]), "")
        feedback = (
            f"Local Frontier-CS evaluator: {valid}/{len(jobs)} cases with positive score; "
            f"average ratio={total_ratio:.6f}."
        )
        if details:
            feedback += f" First diagnostic: {details}"
        return self.score(
            score,
            feedback=feedback,
            metadata={"cases": len(jobs), "positive_cases": valid, "average_ratio": total_ratio},
        )
