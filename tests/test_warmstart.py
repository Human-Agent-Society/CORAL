"""Tests for warm-start system: research prompts."""

from coral.agent.warmstart import WarmStartRunner
from coral.config import AgentConfig, CoralConfig, TaskConfig, WarmStartConfig


def _make_config(
    count: int = 1,
    enabled: bool = True,
) -> CoralConfig:
    return CoralConfig(
        task=TaskConfig(name="test-task", description="A test task"),
        agents=AgentConfig(
            count=count,
            warmstart=WarmStartConfig(
                enabled=enabled,
            ),
        ),
    )


# --- Property tests ---


def test_enabled_property():
    runner = WarmStartRunner(_make_config(enabled=True))
    assert runner.enabled is True

    runner = WarmStartRunner(_make_config(enabled=False))
    assert runner.enabled is False


# --- Research prompt tests ---


def test_research_prompt_contains_shared_dir():
    runner = WarmStartRunner(_make_config(), shared_dir=".claude")
    prompt = runner.research_prompt()
    assert ".claude/notes/" in prompt
    assert "Do NOT" in prompt


def test_research_prompt_different_shared_dir():
    runner = WarmStartRunner(_make_config(), shared_dir=".opencode")
    prompt = runner.research_prompt()
    assert ".opencode/notes/" in prompt


# --- Main prompt tests ---


def test_main_prompt_references_notes():
    runner = WarmStartRunner(_make_config(), shared_dir=".claude")
    prompt = runner.main_prompt()
    assert ".claude/notes/" in prompt
    assert "Begin" in prompt


def test_main_prompt_different_shared_dir():
    runner = WarmStartRunner(_make_config(), shared_dir=".codex")
    prompt = runner.main_prompt()
    assert ".codex/notes/" in prompt
