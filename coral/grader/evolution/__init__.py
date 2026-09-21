"""Versioned, artifact-grounded evolution of evaluation criteria.

Wraps any criteria-driven ``TaskGrader`` so its rubric can grow during a run:
at fixed checkpoints on the scored-observation clock, a proposer is shown the recent
trajectory (evaluator feedback, staged artifacts, agents' notes), proposes
criteria that must quote the evidence they rest on, and whatever survives a
mechanical admission filter is published as a new immutable rubric version.
Every score is bound to the version it was scored under; every prompt an agent
receives after a publication is recorded, so "was this agent exposed to this
change?" is a question the run directory can answer.

    state.py           immutable snapshots, the event ledger, decision records
    policy.py          arm, checkpoint schedule, slot budget
    proposals.py       evidence staging, the proposer call, grounding + admission
    failures.py        structured evaluation-failure codes
    grader.py          EvolvingTaskGrader: static / adaptive / yoked arms
    schedule.py        export a finished adaptive run's schedule for its yoke
    injection_scan.py  post-hoc scan of what the proposer was shown

Wrap a grader by subclassing and naming the inner class::

    class EvolvingMyGrader(EvolvingTaskGrader):
        inner_grader_cls = MyGrader

See README.md in this directory for the design.
"""

from coral.grader.evolution.failures import FailureCode, FailureRecord, classify_generic
from coral.grader.evolution.grader import EvolvingTaskGrader
from coral.grader.evolution.policy import PolicyConfig
from coral.grader.evolution.state import (
    Criterion,
    EvolutionStore,
    Observation,
    RubricSnapshot,
)

__all__ = [
    "Criterion",
    "EvolutionStore",
    "EvolvingTaskGrader",
    "FailureCode",
    "FailureRecord",
    "Observation",
    "PolicyConfig",
    "RubricSnapshot",
    "classify_generic",
]
