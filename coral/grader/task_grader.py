"""TaskGrader base class — the single way to write graders for CORAL tasks.

Task authors create eval/grader.py in their task directory, inheriting from
TaskGrader and implementing evaluate():

    from coral.grader import TaskGrader

    class Grader(TaskGrader):
        def evaluate(self) -> float:
            return 0.85
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from coral.config import GraderConfig
from coral.types import Score, ScoreBundle, Task


class TaskGrader(ABC):
    """Base class for task graders.

    Subclasses implement evaluate() and return a float or ScoreBundle.
    The framework sets codebase_path, private_dir, config, args, and tasks
    before calling.
    """

    codebase_path: str
    private_dir: str
    config: GraderConfig
    tasks: list[Task]

    def __init__(self, config: GraderConfig) -> None:
        self.config = config
        self.tasks = []

    @property
    def args(self) -> dict[str, Any]:
        """Grader-specific args from config."""
        return self.config.args

    @property
    def timeout(self) -> int | None:
        """Eval timeout in seconds, from grader config. None means no limit."""
        return self.config.timeout or None

    @property
    def tune(self) -> bool:
        """True if this attempt was submitted with `coral eval --tune`.

        Use this to switch your grader to a cheaper local target — a smaller
        eval slice, dev split, or smoke harness — when the agent is sweeping
        hyperparameters or shaking out config rather than making a real
        submission. The agent will not be charged against its plateau /
        heartbeat budget for tune-mode attempts (see issue #73).

        False for the standard ``coral eval`` path.
        """
        if not self.tasks:
            return False
        return bool(self.tasks[0].metadata.get("tune", False))

    @property
    def budget_class(self) -> str:
        """The pending attempt's budget class: "real" or "tune".

        Note: "infra" is assigned by the daemon *after* grading (when the
        grader times out or raises), so this property only ever returns
        "real" or "tune".
        """
        if not self.tasks:
            return "real"
        return str(self.tasks[0].metadata.get("budget_class", "real"))

    def describe_tune(self) -> str:
        """Per-task contract for what `coral eval --tune` does on this grader.

        Override this to tell the agent what is actually different about a
        tune-mode evaluation on your task — e.g. "scored on a 10% subset of
        the validation set; runs in ~30s instead of ~5m; the tune score is
        an unbiased but noisier estimate of the real score." The string is
        rendered into the agent's CORAL.md so it shows up alongside the
        `--tune` documentation. Plain prose; markdown is allowed.

        The default below is correct for graders that have not bothered to
        differentiate tune from real: tune is a pure budget-classification
        flag and the score returned is identical. If your grader does
        nothing special for tune mode, leave the default — it is honest.
        """
        return (
            "This grader does not differentiate tune mode from a real "
            "submission: scoring runs the full evaluation either way and "
            "returns the same score it would return without `--tune`. "
            "The flag's only effect is budget classification — tune "
            "attempts do not count against the plateau / heartbeat budget."
        )

    @property
    def eval_logs_dir(self) -> Path:
        """Per-attempt directory for eval artifacts that should outlive the grader.

        The grader runs in an isolated checkout that the daemon force-removes
        after each eval (see coral/grader/daemon.py:_remove_worktree), so
        anything written under self.codebase_path is lost. Use this dir for
        subprocess logs, terminal recordings, traces, etc. the agent should
        be able to inspect after the eval finishes.

        Path: .coral/public/eval_logs/<checkout_dir_name>/
        (= attempt commit hash when invoked by the grader daemon)

        Symlinked into each agent worktree at `<worktree>/.claude/eval_logs/`
        by setup_shared_state.
        """
        d = (
            Path(self.private_dir).parent
            / "public" / "eval_logs"
            / Path(self.codebase_path).name
        )
        d.mkdir(parents=True, exist_ok=True)
        return d

    def eval_logs_worktree_path(self, abs_path: Path) -> Path:
        """Return an eval_logs absolute path as `eval_logs/<...>` (runtime-agnostic).

        The grader's eval_logs dir is symlinked into each agent worktree under
        the runtime's shared state dir (e.g. `.claude/eval_logs/`,
        `.codex/eval_logs/`, ...). Print the no-prefix form so agents on any
        runtime can prepend their own shared dir to access it via Read.

        Falls back to the original absolute path if it isn't under eval_logs/.
        """
        parts = Path(abs_path).parts
        try:
            idx = parts.index("eval_logs")
        except ValueError:
            return Path(abs_path)
        return Path(*parts[idx:])

    @abstractmethod
    def evaluate(self) -> float | ScoreBundle:
        """Implement this. Return a numeric score or a ScoreBundle."""
        ...

    # --- Helpers ---

    def get_python_command(self) -> list[str]:
        """Return the Python command for running task programs.

        Uses ``uv run`` when a ``pyproject.toml`` exists in the codebase so
        that task-specific dependencies (numpy, scipy, …) are available.
        Falls back to the current interpreter otherwise.
        """
        import shutil
        import sys

        if (Path(self.codebase_path) / "pyproject.toml").exists() and shutil.which("uv"):
            return ["uv", "run", "--project", self.codebase_path, "python"]
        return [sys.executable]

    def run_program(
        self,
        filename: str,
        *cmd_args: str,
    ) -> subprocess.CompletedProcess[str]:
        """Run a file from the agent's codebase in a subprocess."""
        filepath = Path(self.codebase_path) / filename
        if not filepath.exists():
            raise FileNotFoundError(f"{filename} not found in codebase")
        return subprocess.run(
            [*self.get_python_command(), str(filepath), *cmd_args],
            capture_output=True,
            text=True,
            cwd=self.codebase_path,
            timeout=self.timeout,
        )

    def run_script(
        self,
        script: str,
        *,
        timeout: int = 300,
    ) -> subprocess.CompletedProcess[str]:
        """Run an inline Python script using the correct interpreter."""
        return subprocess.run(
            [*self.get_python_command(), "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def run_script_json(
        self,
        script: str,
        *,
        timeout: int = 300,
    ) -> dict:
        """Run an inline script that prints JSON to stdout and return parsed dict.

        Handles common failure modes:
        - Non-zero exit: raises RuntimeError with stderr
        - Empty stdout: raises RuntimeError with stderr for diagnostics
        - Stdout polluted by print statements: scans for last JSON line
        """
        result = self.run_script(script, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip()[-2000:])
        stdout = result.stdout.strip()
        if not stdout:
            stderr_tail = result.stderr.strip()[-1000:]
            raise RuntimeError(
                f"Script produced no output on stdout.\nstderr: {stderr_tail}"
            )
        # Try full stdout first
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            pass
        # Scan lines in reverse for a JSON object (handles print() pollution)
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        raise RuntimeError(
            f"No valid JSON in script output.\n"
            f"stdout (last 500): {stdout[-500:]}\n"
            f"stderr (last 500): {result.stderr.strip()[-500:]}"
        )

    def read_eval(self, relative_path: str) -> str:
        """Read a file from the eval/ directory (inside .coral/private/eval/)."""
        path = Path(self.private_dir) / "eval" / relative_path
        if not path.exists():
            raise FileNotFoundError(f"Eval file not found: {relative_path}")
        return path.read_text()

    def read_eval_path(self, relative_path: str) -> Path:
        """Get the absolute path to a file in eval/."""
        return Path(self.private_dir) / "eval" / relative_path

    def score(
        self, value: float | None, explanation: str = "", feedback: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ScoreBundle:
        """Return a single-score bundle."""
        return self.bundle(value, explanation, feedback=feedback, metadata=metadata)

    def fail(self, explanation: str = "", feedback: str | None = None) -> ScoreBundle:
        """Return a bundle with a null score (evaluation failed)."""
        return self.bundle(None, explanation, feedback=feedback)

    def bundle(
        self, value: float | None, explanation: str = "", feedback: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ScoreBundle:
        """Create a ScoreBundle from a score value and explanation."""
        s = Score(
            value=value,
            name="eval",
            explanation=explanation or None,
        )
        return ScoreBundle(
            scores={"eval": s},
            aggregated=value,
            feedback=feedback,
            metadata=metadata or {},
        )

    # --- Internal: called by the framework ---

    async def grade(
        self,
        codebase_path: str,
        tasks: list[Task],
        **kwargs: Any,
    ) -> ScoreBundle:
        """GraderInterface implementation. Sets context and calls evaluate().

        Enforces self.timeout around the entire evaluate() call.
        """
        self.codebase_path = codebase_path
        self.tasks = tasks

        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(pool, self.evaluate),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                return self.fail(f"Evaluation timed out after {self.timeout}s")

        if isinstance(result, ScoreBundle):
            return result

        # float/int — wrap in a ScoreBundle
        value = float(result)
        return ScoreBundle(
            scores={"eval": Score(value=value, name="eval")},
            aggregated=value,
        )
