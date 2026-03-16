"""Read/list .coral/public/skills/<name>/SKILL.md with directory trees."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


def _skills_dir(coral_dir: str | Path) -> Path:
    d = Path(coral_dir) / "public" / "skills"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if m:
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
        return meta, m.group(2)
    return {}, text


def list_skills(coral_dir: str | Path) -> list[dict[str, Any]]:
    """List all skills with name + description from SKILL.md frontmatter."""
    d = _skills_dir(coral_dir)
    results = []
    for skill_dir in sorted(d.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        text = skill_md.read_text()
        meta, body = _parse_frontmatter(text)

        results.append({
            "name": meta.get("name", skill_dir.name),
            "description": meta.get("description", ""),
            "creator": meta.get("creator", "unknown"),
            "created": str(meta["created"]) if meta.get("created") else "",
            "path": str(skill_dir),
        })
    return results


def format_skills_list(skills: list[dict[str, Any]]) -> str:
    """Format skills list for terminal display."""
    if not skills:
        return "No skills yet."
    lines = []
    for i, sk in enumerate(skills, 1):
        desc = sk.get("description", "")
        desc_str = f" — {desc}" if desc else ""
        lines.append(f"  {i}. {sk['name']}{desc_str}")
    return "\n".join(lines)


def read_skill(skill_dir: str | Path) -> dict[str, Any]:
    """Read a skill's SKILL.md content and list all files in the directory."""
    skill_dir = Path(skill_dir)
    skill_md = skill_dir / "SKILL.md"

    content = skill_md.read_text() if skill_md.exists() else ""
    meta, body = _parse_frontmatter(content)

    files = []
    for f in sorted(skill_dir.rglob("*")):
        if f.is_file():
            files.append(str(f.relative_to(skill_dir)))

    return {
        "content": content,
        "metadata": meta,
        "body": body,
        "files": files,
    }


def get_skill_tree(skill_dir: str | Path) -> str:
    """Get a formatted file tree of the skill directory."""
    skill_dir = Path(skill_dir)
    lines = [f"{skill_dir.name}/"]

    def _tree(directory: Path, prefix: str = "") -> None:
        entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name))
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "  " if is_last else "  "
            lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
            if entry.is_dir():
                extension = "   " if is_last else "   "
                _tree(entry, prefix + extension)

    _tree(skill_dir)
    return "\n".join(lines)
