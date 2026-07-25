"""Topology-agnostic behavior diagnostics for literal-bit search runs."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any


def hamming(left: str, right: str) -> int:
    if len(left) != len(right):
        raise ValueError("candidates must have the same length")
    return sum(a != b for a, b in zip(left, right, strict=True))


def normalized_entropy(counts: dict[str, int]) -> float:
    total = sum(counts.values())
    active = sum(value > 0 for value in counts.values())
    if total == 0 or active <= 1:
        return 0.0
    entropy = -sum((value / total) * math.log(value / total) for value in counts.values() if value)
    return entropy / math.log(active)


def _operator(distance: int, n: int) -> str:
    if distance <= 4:
        return "local"
    if distance >= max(8, n // 4):
        return "restart"
    return "structured"


def _mean_pairwise_jaccard(groups: dict[str, set[int]]) -> float:
    values = list(groups.values())
    pairs = []
    for index, left in enumerate(values):
        for right in values[index + 1 :]:
            union = left | right
            pairs.append(len(left & right) / len(union) if union else 0.0)
    return statistics.fmean(pairs) if pairs else 0.0


def behavior_metrics(
    parsed: list[tuple[dict[str, Any], str]],
    *,
    local_parent_radius: int = 4,
) -> dict[str, Any]:
    """Infer mutation modes and cross-agent lineage adoption from attempts.

    The inference is deliberately conservative. A candidate is attributed to
    another agent only when it is within ``local_parent_radius`` of a prior
    foreign candidate and strictly closer to that candidate than to the
    submitting agent's own previous candidate.
    """

    previous_by_agent: dict[str, str] = {}
    lineage_by_agent: dict[str, str] = {}
    prior: list[tuple[str, str, str]] = []
    operator_counts = {"local": 0, "structured": 0, "restart": 0}
    touched: dict[str, set[int]] = defaultdict(set)
    transitions = 0
    inferred_adoptions = 0
    exact_foreign_copies = 0
    lineage_total = 0.0
    lineage_observations = 0

    for record, candidate in parsed:
        agent = str(record.get("agent_id") or "unknown")
        own_previous = previous_by_agent.get(agent)
        if own_previous is None:
            lineage_by_agent[agent] = agent
        else:
            transitions += 1
            own_distance = hamming(own_previous, candidate)
            parent = own_previous
            parent_distance = own_distance

            foreign = [
                (
                    hamming(prior_candidate, candidate),
                    prior_agent,
                    prior_lineage,
                    prior_candidate,
                )
                for prior_agent, prior_candidate, prior_lineage in prior
                if prior_agent != agent
            ]
            if foreign:
                foreign_distance, _foreign_agent, foreign_lineage, foreign_parent = min(foreign)
                if foreign_distance == 0:
                    exact_foreign_copies += 1
                if foreign_distance <= local_parent_radius and foreign_distance < own_distance:
                    inferred_adoptions += 1
                    lineage_by_agent[agent] = foreign_lineage
                    parent = foreign_parent
                    parent_distance = foreign_distance

            operator_counts[_operator(parent_distance, len(candidate))] += 1
            if parent_distance <= local_parent_radius:
                touched[agent].update(
                    index
                    for index, (left, right) in enumerate(zip(parent, candidate, strict=True))
                    if left != right
                )

        previous_by_agent[agent] = candidate
        lineage = lineage_by_agent[agent]
        prior.append((agent, candidate, lineage))
        lineage_total += len(set(lineage_by_agent.values()))
        lineage_observations += 1

    return {
        "behavior_transitions": transitions,
        "local_transition_rate": (operator_counts["local"] / transitions if transitions else 0.0),
        "structured_transition_rate": (
            operator_counts["structured"] / transitions if transitions else 0.0
        ),
        "restart_transition_rate": (
            operator_counts["restart"] / transitions if transitions else 0.0
        ),
        "operator_entropy": normalized_entropy(operator_counts),
        "local_coordinate_overlap": _mean_pairwise_jaccard(touched),
        "inferred_cross_agent_adoptions": inferred_adoptions,
        "inferred_cross_agent_adoption_rate": (
            inferred_adoptions / transitions if transitions else 0.0
        ),
        "exact_foreign_copies": exact_foreign_copies,
        "final_inferred_lineages": len(set(lineage_by_agent.values())),
        "mean_active_inferred_lineages": (
            lineage_total / lineage_observations if lineage_observations else 0.0
        ),
    }
