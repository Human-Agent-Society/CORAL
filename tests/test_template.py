"""Tests for CORAL.md template generation."""

from coral.config import AgentConfig, CoralConfig, GraderConfig, TaskConfig
from coral.template.coral_md import generate_coral_md


def test_generate_coral_md_has_required_sections():
    config = CoralConfig(
        task=TaskConfig(
            name="Kernel Optimization",
            description="Optimize the kernel for speed.",
            tips="Profile first!",
        ),
        grader=GraderConfig(direction="minimize"),
        agents=AgentConfig(count=2),
    )

    md = generate_coral_md(config, "agent-1")

    # Task info
    assert "Kernel Optimization" in md
    assert "Optimize the kernel for speed" in md

    # Tips
    assert "Profile first!" in md

    # Agent identity
    assert "agent-1" in md
    assert "creator: agent-1" in md

    # Score direction comes from grader.direction now (no type-based table)
    assert "lower is better" in md

    # Core structure
    assert "Orientation" in md
    assert "## 1. Plan" in md
    assert "## 2. Edit" in md
    assert "## 3. Evaluate" in md
    assert "## 5. Share Knowledge" in md
    assert "Ground Rules" in md

    # Key behavioral instructions
    assert "fully autonomous" in md
    assert "Do not duplicate effort" in md
    assert "Keep iterating" in md

    # Multi-agent awareness
    assert "several agents" in md
    assert "other agents" in md

    # Shared state
    assert "coral log --search" in md
    assert ".claude/notes" in md
    assert ".claude/skills/" in md


def test_generate_coral_md_without_optional_sections():
    config = CoralConfig(
        task=TaskConfig(name="Simple Task", description="Do the thing."),
        grader=GraderConfig(),
    )

    md = generate_coral_md(config, "agent-5")

    assert "Simple Task" in md
    assert "Do the thing." in md
    assert "agent-5" in md
    assert "## Key Files" not in md
    assert "## Tips" not in md
    assert "higher is better" in md


def test_generate_coral_md_single_agent():
    """Single-agent template omits multi-agent sharing references."""
    config = CoralConfig(
        task=TaskConfig(
            name="Solo Task",
            description="Optimize alone.",
            tips="Be thorough.",
        ),
        grader=GraderConfig(),
        agents=AgentConfig(count=1),
    )

    md = generate_coral_md(config, "agent-1", single_agent=True)

    # Core content present
    assert "Solo Task" in md
    assert "Optimize alone." in md
    assert "Be thorough." in md
    assert "agent-1" in md
    assert "fully autonomous" in md
    assert "Keep iterating" in md

    # Multi-agent references absent
    assert "several agents" not in md
    assert "other agents" not in md
    assert "Share Knowledge" not in md
    assert "Do not duplicate effort" not in md

    # Single-agent still has notes/skills (for self-use)
    assert "notes" in md.lower()
    assert "skills" in md.lower()
    assert "Record Knowledge" in md


def test_generate_coral_md_score_direction_from_config():
    """Score direction now comes solely from grader.direction (no type table)."""
    for direction, expected in [
        ("maximize", "higher is better"),
        ("minimize", "lower is better"),
    ]:
        config = CoralConfig(
            task=TaskConfig(name="t", description="d"),
            grader=GraderConfig(direction=direction),
        )
        md = generate_coral_md(config, "agent-1")
        assert expected in md, f"Missing '{expected}' for direction '{direction}'"
