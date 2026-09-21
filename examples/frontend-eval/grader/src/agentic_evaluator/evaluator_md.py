"""Generate EVALUATOR.md from the task config + the runtime context."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "evaluator.md.template"


def _format_criteria(criteria: list[dict[str, Any]]) -> str:
    """Render the criteria section as a markdown list with weights."""
    lines: list[str] = []
    for i, c in enumerate(criteria, 1):
        name = c.get("name", f"Criterion {i}")
        weight = float(c.get("weight", 1.0))
        description = (c.get("description") or "").strip()
        fail_examples = (c.get("fail_examples") or "").strip()

        lines.append(f"### {i}. {name}  (weight: {weight})")
        lines.append("")
        if description:
            lines.append(description)
            lines.append("")
        if fail_examples:
            lines.append("**Things that should drag this score down:**")
            lines.append("")
            lines.append(fail_examples)
            lines.append("")
    return "\n".join(lines).strip()


def generate_evaluator_md(
    *,
    task_name: str,
    task_description: str,
    url: str,
    criteria: list[dict[str, Any]],
    output_path: str,
    scratch_dir: str,
    evaluation_instructions: str = "",
) -> str:
    """Render the evaluator instruction file."""
    template = _TEMPLATE_PATH.read_text()
    return template.format(
        task_name=task_name,
        task_description=task_description.strip(),
        url=url,
        criteria_section=_format_criteria(criteria),
        evaluation_instructions=evaluation_instructions.strip()
        or "Use the protocol below. Customize as the task requires.",
        output_path=output_path,
        scratch_dir=scratch_dir,
    )
