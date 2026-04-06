"""CORAL evaluator: uses eval score improvement as the RL reward.

The generator passes CORAL attempt data through episode.metadata.
This evaluator computes reward as the diff between each attempt's
score and its parent commit's score (score - parent_score).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import rllm
from rllm.experimental.eval.types import EvalOutput, Signal
from rllm.types import Episode

logger = logging.getLogger(__name__)


def _compute_improvement(attempts: list[dict], coral_dir: str) -> tuple[float, float]:
    """Compute score improvement for the latest attempt vs its parent.

    Returns (latest_score, improvement).
    """
    if not attempts:
        return 0.0, 0.0

    attempt = attempts[-1]
    score = attempt.get("score", 0.0) or 0.0
    parent_hash = attempt.get("parent_hash")
    parent_score = 0.0

    if parent_hash and coral_dir:
        parent_path = Path(coral_dir) / "public" / "attempts" / f"{parent_hash}.json"
        if parent_path.exists():
            try:
                parent = json.loads(parent_path.read_text())
                parent_score = parent.get("score", 0.0) or 0.0
            except (json.JSONDecodeError, OSError):
                logger.warning("Failed to read parent attempt: %s", parent_path)

    return score, score - parent_score


@rllm.evaluator
def evaluator(task: dict, episode: Episode) -> EvalOutput:  # noqa: ARG001
    """Compute reward from score improvement over the parent commit.

    episode.metadata is expected to contain:
        - coral_dir: str — path to the .coral directory
        - new_attempts: list[dict] — attempt dicts from this training step
    """
    meta = episode.metadata or {}
    coral_dir = meta.get("coral_dir", "")
    new_attempts = meta.get("new_attempts", [])

    latest_score, improvement = _compute_improvement(new_attempts, coral_dir)

    # Assign the improvement as reward to each trajectory
    for traj in episode.trajectories:
        traj.reward = improvement

    return EvalOutput(
        reward=improvement,
        is_correct=improvement > 0,
        signals=[
            Signal(name="latest_score", value=latest_score),
            Signal(name="improvement", value=improvement),
        ],
    )
