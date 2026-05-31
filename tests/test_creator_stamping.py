"""Bundled prompts and subagent templates instruct agents to stamp `creator:`.

Migration filters notes/skills by frontmatter `creator: <agent_id>`. If the
canonical heartbeat prompt and the bundled subagent / skill-creator templates
do not tell agents to stamp it, migration will silently drop their work.
This test is the regression gate for that instruction surviving future
prompt edits.
"""

from pathlib import Path

COMMON_INSTRUCTION_KEYWORDS = ["creator:", "frontmatter"]


def _check_prompt(path: Path) -> None:
    text = path.read_text().lower()
    for kw in COMMON_INSTRUCTION_KEYWORDS:
        assert kw in text, f"{path} must mention {kw!r} so agents stamp the creator field"


def test_consolidate_prompt_instructs_creator_stamping():
    _check_prompt(Path("coral/hub/prompts/consolidate.md"))


def test_librarian_template_instructs_creator_stamping():
    _check_prompt(Path("coral/template/agents/librarian.md"))


def test_skill_creator_template_instructs_creator_stamping():
    _check_prompt(Path("coral/template/skills/skill-creator/SKILL.md"))


def test_bundled_skill_md_files_have_no_creator_frontmatter():
    """Bundled skills must not have `creator:` in their SKILL.md frontmatter, so
    migration's `skills_by` filter correctly excludes them."""
    bundled = Path("coral/template/skills").rglob("SKILL.md")
    for skill_md in bundled:
        text = skill_md.read_text()
        # Only inspect frontmatter (first --- block); body may legitimately mention "creator"
        if not text.startswith("---"):
            continue
        end = text.find("---", 3)
        front = text[3:end]
        assert "\ncreator:" not in front and not front.startswith("creator:"), (
            f"{skill_md} has stray `creator:` in frontmatter — would migrate as agent-authored"
        )
