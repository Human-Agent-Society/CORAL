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
        grader=GraderConfig(type="kernel_builder"),
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

    # Score direction (kernel_builder specific)
    assert "lower cycle count is better" in md

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
        grader=GraderConfig(type="function"),
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
        grader=GraderConfig(type="function"),
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


def test_generate_coral_md_score_directions():
    for grader_type, expected_fragment in [
        ("kernel_builder", "lower cycle count"),
        ("swebench", "pass rate"),
        ("terminalbench", "pass rate"),
        ("function", "higher is better"),
        ("unknown_type", "higher is better"),
    ]:
        config = CoralConfig(
            task=TaskConfig(name="t", description="d"),
            grader=GraderConfig(type=grader_type),
        )
        md = generate_coral_md(config, "agent-1")
        assert expected_fragment in md, f"Missing '{expected_fragment}' for grader type '{grader_type}'"
