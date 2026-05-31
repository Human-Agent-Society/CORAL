"""Resolve per-agent runtime/model assignments for multi-agent runs.

Supports two modes:

1. Uniform — ``agents.assignments`` is empty: every agent uses the top-level
   ``agents.runtime`` / ``agents.model`` / ``agents.runtime_options``.
   ``agents.count`` controls how many agents are spawned.

2. Mix-and-match — ``agents.assignments`` is set: each assignment spawns
   ``count`` agents using its own ``runtime`` / ``model`` / ``runtime_options``.
   Total agent count is the sum across assignments; ``agents.count`` is
   ignored. Empty fields on an assignment inherit from the top-level
   ``agents.*`` defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from coral.agent.registry import default_model_for_runtime
from coral.config import CoralConfig


@dataclass(frozen=True)
class AgentSpec:
    """Concrete spawn parameters for a single agent."""

    agent_id: str
    runtime: str
    model: str
    runtime_options: dict[str, Any] = field(default_factory=dict)
    # Index into ``agents.assignments`` this agent came from, or None when the
    # run is in uniform mode (no assignments list).
    assignment_index: int | None = None
    # Birth island ID after partitioning (e.g. "0", "1"). None in single-island
    # mode. Stable across migration — the prefix on ``agent_id`` always reflects
    # birth island, while this field can be repointed in Phase 3 if needed.
    island_id: str | None = None


def resolve_agent_specs(config: CoralConfig) -> list[AgentSpec]:
    """Expand a config into the concrete per-agent specs the manager will spawn.

    Always returns at least one spec. Agent IDs are ``agent-1``, ``agent-2``,
    ... in spawn order. When ``agents.assignments`` is empty the function
    falls back to ``agents.count`` copies of the top-level defaults.
    """
    base_runtime = config.agents.runtime
    base_model = config.agents.model
    base_options = dict(config.agents.runtime_options)
    assignments = list(config.agents.assignments)

    specs: list[AgentSpec] = []

    if not assignments:
        total = max(1, config.agents.count)
        for i in range(total):
            specs.append(
                AgentSpec(
                    agent_id=f"agent-{i + 1}",
                    runtime=base_runtime,
                    model=base_model,
                    runtime_options=dict(base_options),
                    assignment_index=None,
                )
            )
        return specs

    next_idx = 1
    for assignment_idx, assignment in enumerate(assignments):
        runtime = assignment.runtime or base_runtime
        model = assignment.model
        if not model:
            # Empty model on the assignment: prefer the runtime-specific default
            # if the assignment's runtime differs from the top-level default,
            # otherwise fall back to agents.model.
            if assignment.runtime and assignment.runtime != base_runtime:
                model = default_model_for_runtime(assignment.runtime) or base_model
            else:
                model = base_model
        options = dict(base_options)
        options.update(assignment.runtime_options)
        for _ in range(assignment.count):
            specs.append(
                AgentSpec(
                    agent_id=f"agent-{next_idx}",
                    runtime=runtime,
                    model=model,
                    runtime_options=dict(options),
                    assignment_index=assignment_idx,
                )
            )
            next_idx += 1

    return specs


def specs_use_multiple_runtimes(specs: list[AgentSpec]) -> bool:
    """Return True iff the resolved specs cover more than one distinct runtime."""
    return len({s.runtime for s in specs}) > 1


def partition_into_islands(
    specs: list[AgentSpec],
    count: int,
) -> list[AgentSpec]:
    """Distribute resolved agent specs across `count` islands round-robin.

    Returns a new list of AgentSpecs with ``island_id`` populated and
    ``agent_id`` rewritten to ``<birth_island>-agent-<per-island-seq>``
    when count > 1. When count == 1, returns the input unchanged (no
    ID rewriting, ``island_id`` stays None) — preserves today's single-island
    behavior exactly.

    Round-robin: spec i lands on island ``i % count``. The per-island sequence
    is the order each island sees specs (so the first spec landing on island 2
    is ``2-agent-1`` regardless of its global index).

    Raises:
        ValueError: if count < 1.
    """
    if count < 1:
        raise ValueError(f"count must be >= 1, got {count}")
    if count == 1:
        return list(specs)

    per_island_seq: dict[str, int] = {}
    out: list[AgentSpec] = []
    for global_idx, spec in enumerate(specs):
        island_id = str(global_idx % count)
        per_island_seq[island_id] = per_island_seq.get(island_id, 0) + 1
        seq = per_island_seq[island_id]
        new_id = f"{island_id}-agent-{seq}"
        out.append(
            AgentSpec(
                agent_id=new_id,
                runtime=spec.runtime,
                model=spec.model,
                runtime_options=dict(spec.runtime_options),
                assignment_index=spec.assignment_index,
                island_id=island_id,
            )
        )
    return out
