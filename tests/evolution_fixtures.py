"""Shared fixtures and helpers for the evolving-evaluation protocol tests."""

from __future__ import annotations  # noqa: F401

import json  # noqa: F401
from pathlib import Path  # noqa: F401

import pytest  # noqa: F401

from coral.grader.evolution import grader as gmod  # noqa: F401
from coral.grader.evolution import policy as pol  # noqa: F401
from coral.grader.evolution.state import Criterion, EvolutionStore, RubricSnapshot  # noqa: F401
from coral.hub.attempts import (  # noqa: F401
    claim_attempt,
    finalize_attempt,
    read_attempt,
    write_attempt,
)
from coral.types import Attempt, ScoreBundle  # noqa: F401
from tests.evolution_harness import (  # noqa: F401
    Harness,
    criteria,
    ground,
    proposal,
    reset,
    run_scored,
)

REPO = Path(__file__).resolve().parents[1]

FIVE = criteria(
    ("Build Smoothness", 1.0, False),
    ("Implementation Quality", 1.0, False),
    ("Instruction Following", 1.0, False),
    ("Visual Quality", 1.0, False),
    ("Interaction Experience", 1.0, False),
)
HI = {c["name"]: 0.9 for c in FIVE}

#: Gates wide open so a test needs a handful of attempts, not fifty.
#: A checkpoint at every attempt: the proposer is consulted on each grade, so a
#: test needs a handful of attempts, not fifty.
OPEN = {
    "mode": "adaptive",
    "window": 2,
    "checkpoints": list(range(1, 60)),
    "max_criteria": 11,
    "max_new_criteria_per_round": 2,
    "expansion_weight": 1.0,
}


def _attempt(commit, status="pending", score=None, feedback="", agent="a"):
    return Attempt(
        commit_hash=commit,
        agent_id=agent,
        title="t",
        score=score,
        status=status,
        parent_hash=None,
        timestamp="2026-09-05T00:00:00+00:00",
        feedback=feedback,
    )


def _event(attempt_id, aggregated, scores, version=1):
    return {
        "attempt_id": attempt_id,
        "outcome": "scored",
        "rubric_version_scored": version,
        "aggregated": aggregated,
        "scores": scores,
    }


def _proposer(*names):
    """A stub proposer returning the given criteria, recording every prompt."""

    def fake(*, model, prompt, scratch_cwd, timeout=180):
        fake.prompts.append(prompt)
        return {
            "new_criteria": ground(
                prompt, [proposal(n, cited_evidence=f"evidence for {n}") for n in names]
            ),
            "notes": "stub",
        }

    fake.prompts = []
    return fake


# --------------------------------------------------------------------------- #
# One grader owns one attempt, from evaluation through both writes             #
# --------------------------------------------------------------------------- #


def _adaptive_run(harness, monkeypatch, n=6, names=("Alpha", "Beta")):
    monkeypatch.setattr(gmod.prop, "run_evolution_agent", _proposer(*names))
    for i in range(n):
        run_scored(harness, f"a{i}", FIVE, HI, OPEN, agent_id=f"ag{i % 4}")
    return EvolutionStore(harness.private)


def _filter(props, sources, tmp_path):
    """Run only the admission filter, against a throwaway store."""
    snap = RubricSnapshot(version=1, criteria=[Criterion("Seed", "d")])
    store = EvolutionStore(tmp_path)
    return gmod.prop.filter_proposals(props, snap, store, pol.PolicyConfig(), 5, sources)


CHECKPOINTED = {**OPEN, "checkpoints": [3, 5], "window": 2}
