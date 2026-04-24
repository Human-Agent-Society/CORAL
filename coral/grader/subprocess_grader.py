"""Subprocess-based grader: loads an entrypoint inside .coral/private/grader_venv/.

Used when `task.yaml` declares `grader.entrypoint = "module.path:ClassName"`.
The worker subprocess runs the grader inside the CORAL-managed venv, isolating
its dependencies from CORAL's own venv and keeping the grader source out of the
agent's worktree environment.

Communication is JSON over stdin/stdout. Exceptions raised inside the worker
are returned as `{"error": ..., "traceback": ...}` and re-raised in the parent.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from coral.config import GraderConfig
from coral.types import ScoreBundle, Task

logger = logging.getLogger(__name__)


# Inline worker script. Runs in the grader venv (where coral and the user's
# grader package are installed). Reads JSON payload from stdin, writes JSON
# response to stdout. Exits 0 in all cases — error info goes in the JSON.
_WORKER_SCRIPT = r"""
import sys, json, asyncio, traceback, importlib


def _resolve_entrypoint(spec):
    if ":" not in spec:
        raise ValueError(
            f"grader.entrypoint must be 'module.path:ClassName', got {spec!r}"
        )
    mod_path, cls_name = spec.rsplit(":", 1)
    module = importlib.import_module(mod_path)
    cls = getattr(module, cls_name, None)
    if cls is None:
        raise ImportError(
            f"Module {mod_path!r} has no attribute {cls_name!r}"
        )
    return cls


def _main():
    payload = json.loads(sys.stdin.read())

    cls = _resolve_entrypoint(payload["entrypoint"])

    from coral.config import GraderConfig
    from coral.grader.task_grader import TaskGrader
    from coral.types import Task

    if not isinstance(cls, type) or not issubclass(cls, TaskGrader):
        raise TypeError(
            f"{payload['entrypoint']} must resolve to a TaskGrader subclass, "
            f"got {cls!r}"
        )

    config = GraderConfig(**payload["config"])
    grader = cls(config=config)
    grader.private_dir = payload["private_dir"]

    tasks = [Task.from_dict(t) for t in payload["tasks"]]
    bundle = asyncio.run(grader.grade(payload["codebase_path"], tasks))

    sys.stdout.write(json.dumps({"bundle": bundle.to_dict()}))


try:
    _main()
except Exception as exc:  # noqa: BLE001
    sys.stdout.write(
        json.dumps({"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()})
    )
"""


def _grader_config_to_dict(config: GraderConfig) -> dict[str, Any]:
    """JSON-safe representation of GraderConfig for the worker."""
    return dataclasses.asdict(config)


def _parse_worker_response(stdout: str) -> dict[str, Any]:
    """Extract the JSON object from the worker's stdout.

    Tolerates stray prints by scanning for the last `{...}` line.
    """
    text = stdout.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    raise RuntimeError(f"Worker did not return JSON. stdout: {text[-500:]}")


class SubprocessGrader:
    """GraderInterface that spawns a worker in `.coral/private/grader_venv/`."""

    private_dir: str
    config: GraderConfig

    def __init__(
        self,
        entrypoint: str,
        worker_python: Path,
        config: GraderConfig,
        private_dir: str,
    ) -> None:
        self.entrypoint = entrypoint
        self.worker_python = Path(worker_python)
        self.config = config
        self.private_dir = private_dir

    @property
    def timeout(self) -> int | None:
        return self.config.timeout or None

    async def grade(
        self,
        codebase_path: str,
        tasks: list[Task],
        **kwargs: Any,
    ) -> ScoreBundle:
        payload = {
            "entrypoint": self.entrypoint,
            "config": _grader_config_to_dict(self.config),
            "private_dir": self.private_dir,
            "codebase_path": codebase_path,
            "tasks": [t.to_dict() for t in tasks],
        }
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run_worker, payload)

    def _run_worker(self, payload: dict[str, Any]) -> ScoreBundle:
        try:
            result = subprocess.run(
                [str(self.worker_python), "-c", _WORKER_SCRIPT],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            from coral.types import Score

            timeout = self.timeout
            return ScoreBundle(
                scores={
                    "eval": Score(
                        value=None,
                        name="eval",
                        explanation=f"Evaluation timed out after {timeout}s",
                    )
                },
                aggregated=None,
                feedback=f"Evaluation timed out after {timeout}s",
            )

        if result.returncode != 0:
            raise RuntimeError(
                f"Grader worker exited {result.returncode}:\n"
                f"stderr: {result.stderr.strip()[-2000:]}\n"
                f"stdout: {result.stdout.strip()[-500:]}"
            )

        response = _parse_worker_response(result.stdout)

        if "error" in response:
            raise RuntimeError(
                f"Grader raised: {response['error']}\n{response.get('traceback', '')}"
            )

        return ScoreBundle.from_dict(response["bundle"])
