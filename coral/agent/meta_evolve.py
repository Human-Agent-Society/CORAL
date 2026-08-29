"""Lift-guided meta-evolve attribution and recommendation helpers."""

from __future__ import annotations

from dataclasses import dataclass

from coral.config import MetaEvolveConfig
from coral.types import Attempt


@dataclass(frozen=True)
class MetaEvolveAttribution:
    """Operator and mutation labels attached to one attempt."""

    operator: str
    mutation: str


def validate_attribution(
    config: MetaEvolveConfig,
    *,
    operator: str | None,
    mutation: str | None,
    tune: bool,
) -> MetaEvolveAttribution | None:
    """Validate CLI attribution before an eval creates a Git commit."""
    if (operator is None) != (mutation is None):
        raise ValueError("--operator and --mutation must be provided together")
    if operator is None or mutation is None:
        if config.enabled and not tune:
            raise ValueError(
                "enabled agents.meta_evolve requires --operator and --mutation for every real eval"
            )
        return None

    normalized_operator = operator.strip()
    normalized_mutation = mutation.strip()
    if not normalized_operator or not normalized_mutation:
        raise ValueError("--operator and --mutation must be non-empty")

    attribution = MetaEvolveAttribution(
        operator=normalized_operator,
        mutation=normalized_mutation,
    )
    if config.enabled:
        configured = {(arm.operator, arm.mutation) for arm in config.arms}
        if (attribution.operator, attribution.mutation) not in configured:
            raise ValueError(
                "meta-evolve attribution must match a configured arm: "
                f"{attribution.operator}/{attribution.mutation}"
            )
    return attribution


def attempt_attribution(attempt: Attempt) -> MetaEvolveAttribution | None:
    """Read valid namespaced attribution from an attempt, tolerating legacy data."""
    raw = attempt.metadata.get("meta_evolve")
    if not isinstance(raw, dict):
        return None
    operator = raw.get("operator")
    mutation = raw.get("mutation")
    if not isinstance(operator, str) or not isinstance(mutation, str):
        return None
    operator = operator.strip()
    mutation = mutation.strip()
    if not operator or not mutation:
        return None
    return MetaEvolveAttribution(operator=operator, mutation=mutation)


def attribution_metadata(
    attribution: MetaEvolveAttribution,
) -> dict[str, dict[str, str]]:
    """Serialize attribution under its Attempt.metadata namespace."""
    return {
        "meta_evolve": {
            "operator": attribution.operator,
            "mutation": attribution.mutation,
        }
    }
