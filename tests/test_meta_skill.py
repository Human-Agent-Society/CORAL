"""The meta-skill admission gate stays wired into every knowledge-authoring path.

Library quality is decided at birth: skill-creator and the librarian are the
two places agents package new skills, and both must route candidates through
the admission standards in skill-creator's references/meta-skill.md; the
same principles (update-vs-new placement, note-vs-skill routing,
discoverability) apply to note creation via create-notes' before-you-write
check. This test is the regression gate for that wiring surviving future
prompt edits.
"""

from pathlib import Path

_META = Path("coral/template/skills/skill-creator/references/meta-skill.md")


def test_meta_skill_document_exists_with_gate():
    text = _META.read_text(encoding="utf-8").lower()
    assert "admission gate" in text
    # The five criteria that make a candidate library-worthy.
    for criterion in ("recurrence", "outcome", "base-model", "overlap", "generalize"):
        assert criterion in text, f"meta-skill.md must keep the {criterion!r} criterion"


def test_skill_creator_routes_through_admission_gate():
    text = Path("coral/template/skills/skill-creator/SKILL.md").read_text(encoding="utf-8")
    assert "references/meta-skill.md" in text
    assert "Admission Gate" in text


def test_librarian_routes_through_admission_gate():
    text = Path("coral/template/agents/librarian.md").read_text(encoding="utf-8")
    assert "skill-creator/references/meta-skill.md" in text


def test_create_notes_applies_admission_principles():
    text = Path("coral/template/skills/create-notes/SKILL.md").read_text(encoding="utf-8")
    assert "Before You Write" in text
    # Update-vs-new placement, note-vs-skill routing, and discoverability.
    assert "update that note" in text
    assert "skill-creator/references/meta-skill.md" in text
    assert "scan-usage" in text
