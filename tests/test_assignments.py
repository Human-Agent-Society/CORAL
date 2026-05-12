"""Tests for mix-and-match agent assignments (per-agent runtime/model)."""

from __future__ import annotations

import pytest

from coral.agent.assignments import (
    AgentSpec,
    resolve_agent_specs,
    specs_use_multiple_runtimes,
)
from coral.config import (
    AgentAssignmentConfig,
    AgentConfig,
    CoralConfig,
    TaskConfig,
)


def _make_config(agents: AgentConfig) -> CoralConfig:
    return CoralConfig(
        task=TaskConfig(name="test", description="A test"),
        agents=agents,
    )


# --- Uniform mode (assignments unset): falls back to agents.count ---


def test_uniform_default_single_agent():
    config = _make_config(AgentConfig())
    specs = resolve_agent_specs(config)
    assert len(specs) == 1
    assert specs[0].agent_id == "agent-1"
    assert specs[0].runtime == "claude_code"
    assert specs[0].model == "sonnet"
    assert specs[0].assignment_index is None


def test_uniform_count_n():
    config = _make_config(AgentConfig(count=4, runtime="codex", model="gpt-5.4"))
    specs = resolve_agent_specs(config)
    assert [s.agent_id for s in specs] == ["agent-1", "agent-2", "agent-3", "agent-4"]
    assert all(s.runtime == "codex" for s in specs)
    assert all(s.model == "gpt-5.4" for s in specs)
    assert all(s.assignment_index is None for s in specs)
    assert not specs_use_multiple_runtimes(specs)


def test_uniform_runtime_options_copied_per_agent():
    """Each agent gets its own dict, so per-agent mutation doesn't leak."""
    config = _make_config(AgentConfig(count=2, runtime_options={"fast_mode": True}))
    specs = resolve_agent_specs(config)
    specs[0].runtime_options["fast_mode"] = False
    assert specs[1].runtime_options == {"fast_mode": True}


# --- Mix-and-match: agents.assignments overrides agents.count ---


def test_assignments_basic_mix():
    config = _make_config(
        AgentConfig(
            count=99,  # ignored when assignments is set
            assignments=[
                AgentAssignmentConfig(runtime="claude_code", model="opus", count=2),
                AgentAssignmentConfig(runtime="codex", model="gpt-5.4", count=1),
            ],
        )
    )
    specs = resolve_agent_specs(config)
    assert [s.agent_id for s in specs] == ["agent-1", "agent-2", "agent-3"]
    assert [s.runtime for s in specs] == ["claude_code", "claude_code", "codex"]
    assert [s.model for s in specs] == ["opus", "opus", "gpt-5.4"]
    assert [s.assignment_index for s in specs] == [0, 0, 1]
    assert specs_use_multiple_runtimes(specs)


def test_assignments_inherit_top_level_runtime():
    """Empty assignment.runtime inherits from agents.runtime."""
    config = _make_config(
        AgentConfig(
            runtime="codex",
            model="gpt-5.4",
            assignments=[
                AgentAssignmentConfig(model="gpt-5.4-mini", count=1),
                AgentAssignmentConfig(runtime="claude_code", model="opus", count=1),
            ],
        )
    )
    specs = resolve_agent_specs(config)
    assert specs[0].runtime == "codex"
    assert specs[0].model == "gpt-5.4-mini"
    assert specs[1].runtime == "claude_code"
    assert specs[1].model == "opus"


def test_assignments_inherit_model_from_runtime_default():
    """Empty model falls back to the default model for the assignment's runtime."""
    config = _make_config(
        AgentConfig(
            runtime="claude_code",
            model="sonnet",
            assignments=[
                # Different runtime, no model -> uses codex default
                AgentAssignmentConfig(runtime="codex", count=1),
                # Same as top-level runtime, no model -> uses agents.model
                AgentAssignmentConfig(count=1),
            ],
        )
    )
    specs = resolve_agent_specs(config)
    assert specs[0].runtime == "codex"
    # codex default model
    assert specs[0].model == "gpt-5.4"
    assert specs[1].runtime == "claude_code"
    assert specs[1].model == "sonnet"


def test_assignments_runtime_options_merge():
    """Assignment options override top-level runtime_options on conflict."""
    config = _make_config(
        AgentConfig(
            runtime_options={"shared": "base", "only_top": "x"},
            assignments=[
                AgentAssignmentConfig(
                    runtime="codex",
                    model="gpt-5.4",
                    count=1,
                    runtime_options={"shared": "override", "only_assignment": "y"},
                ),
            ],
        )
    )
    specs = resolve_agent_specs(config)
    assert specs[0].runtime_options == {
        "shared": "override",
        "only_top": "x",
        "only_assignment": "y",
    }


def test_assignment_count_must_be_positive():
    with pytest.raises(ValueError, match="count must be >= 1"):
        AgentAssignmentConfig(count=0)


# --- Spec is the right shape downstream code can rely on ---


def test_spec_immutable_fields():
    spec = AgentSpec(
        agent_id="agent-1",
        runtime="claude_code",
        model="sonnet",
        runtime_options={},
    )
    with pytest.raises(Exception):
        spec.agent_id = "agent-2"  # type: ignore[misc]
