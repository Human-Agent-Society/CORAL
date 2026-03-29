"""Grader worker function submitted to submitit executor."""

from __future__ import annotations

import asyncio
import traceback

from coral.config import CoralConfig
from coral.grader.loader import load_grader
from coral.queue.types import EvalRequest, EvalResult
from coral.types import Task


def run_grader_job(request: EvalRequest) -> EvalResult:
    """Run grader in a submitit-managed subprocess.

    Loads the grader from config, runs grade(), and returns an EvalResult.
    """
    import sys

    try:
        # Add codebase path to sys.path so task-local modules (e.g. graders) can be imported
        if request.codebase_path not in sys.path:
            sys.path.insert(0, request.codebase_path)

        config = CoralConfig.from_yaml(request.config_path)
        grader = load_grader(config, coral_dir=request.coral_dir)
        task = Task(
            id=config.task.name,
            name=config.task.name,
            description=config.task.description,
            metadata={"files": config.task.files},
        )
        bundle = asyncio.run(grader.grade(request.codebase_path, [task]))

        # Build feedback from bundle
        parts = []
        if bundle.feedback:
            parts.append(bundle.feedback)
        scores_dict = {}
        if bundle.scores:
            for name, s in bundle.scores.items():
                scores_dict[name] = s.to_dict()
                if s.explanation:
                    parts.append(f"{name}: {s.explanation}")

        return EvalResult(
            ticket_id=request.ticket_id,
            score=bundle.aggregated,
            scores=scores_dict,
            feedback="\n".join(parts),
            status="ok",
        )
    except TimeoutError:
        return EvalResult(
            ticket_id=request.ticket_id,
            score=None,
            status="timeout",
            error="Grader timed out",
        )
    except Exception as e:
        return EvalResult(
            ticket_id=request.ticket_id,
            score=None,
            status="error",
            error=f"{e}\n{traceback.format_exc()}",
        )
