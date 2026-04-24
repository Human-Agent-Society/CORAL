"""Generate JUDGE.md instructions for the judge agent."""

from __future__ import annotations

import logging
from pathlib import Path

from coral.config import CoralConfig

from apex_judge.dynamic_rubric_state import RubricStateManager, RubricVersion

logger = logging.getLogger(__name__)

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "judge.md.template"

_MAX_AGENT_NOTES_CHARS = 20_000


def generate_judge_md(
    config: CoralConfig,
    state: RubricStateManager,
    output_path: str,
    scratch_dir: str,
    files: list[str] | None = None,
    reference_context: str = "",
    codebase_path: str = "",
) -> str:
    """Produce the JUDGE.md file that the judge agent reads.

    Args:
        config: The coral config.
        state: Rubric state manager for loading current rubric and history.
        output_path: Absolute path where the judge must write evaluation.json.
        scratch_dir: Absolute path to the judge's scratch directory.
        files: Optional list of expected output file names (relative to ``./codebase/``).
        reference_context: Pre-read reference documents text.
        codebase_path: Absolute path to the agent's worktree (for reading notes).
    """
    template = _TEMPLATE_PATH.read_text()

    # Build files section — paths are relative to the judge's workspace,
    # where the worker's codebase is symlinked as ./codebase/
    if files:
        files_section = "\n".join(f"- `./codebase/{f}`" for f in files)
    else:
        files_section = "- Any `.md` files in `./codebase/` (excluding instruction files)"

    # Build rubric section
    current = state.get_current_version()
    if current is not None:
        rubric_section = _format_rubric(current)
    else:
        rubric_section = _format_initial_rubric_instructions(config)

    # Inject locked criteria from runtime guidance — these are pre-scored
    # by the grader and cannot be modified or retired by the judge.
    runtime_guidance = _read_runtime_guidance(codebase_path) if codebase_path else ""
    locked_criteria = _parse_guidance_into_criteria(runtime_guidance)
    if locked_criteria:
        rubric_section += "\n" + _format_locked_criteria(locked_criteria)

    # Build criterion history
    last_n = 10
    criterion_history = state.get_criterion_summary(last_n=last_n)

    # Build reference section
    if reference_context:
        reference_section = (
            "The following reference documents are available for fact-checking.\n\n"
            + reference_context
        )
    else:
        reference_section = "No reference documents provided."

    # Build agent notes context
    agent_notes_context = (
        _read_agent_notes(codebase_path) if codebase_path else "No agent notes available."
    )

    # Build all-pass context
    if state.was_last_eval_perfect():
        all_pass_context = (
            "**The worker scored PASS on ALL criteria in the most recent evaluation. "
            "Rubric evolution is MANDATORY this round.** You must raise the bar — see instructions below."
        )
    else:
        all_pass_context = ""

    # Build evaluation guidance section
    guidance_parts = []

    if config.task.evaluation_guidance:
        guidance_parts.append(
            "### Evaluation Priorities\n\n"
            "The task author has provided the following guidance on what matters most "
            "for this task. Use this to shape your criteria and scoring priorities.\n\n"
            + config.task.evaluation_guidance.strip()
        )

    evaluation_guidance_section = "\n\n".join(guidance_parts)

    min_criteria = config.grader.args.get("min_criteria", 3)
    max_criteria = config.grader.args.get("max_criteria", 10)

    # Resolve worker's shared dir name from its runtime
    try:
        from coral.agent.registry import get_runtime as _get_runtime

        worker_runtime_name = getattr(config.agents, "runtime", "claude_code")
        worker_runtime = _get_runtime(worker_runtime_name)
        shared_dir = worker_runtime.shared_dir_name
    except Exception:
        shared_dir = ".claude"

    return template.format(
        task_name=config.task.name,
        task_description=config.task.description,
        evaluation_guidance_section=evaluation_guidance_section,
        files_section=files_section,
        rubric_section=rubric_section,
        criterion_history=criterion_history,
        reference_section=reference_section,
        agent_notes_context=agent_notes_context,
        all_pass_context=all_pass_context,
        output_path=output_path,
        scratch_dir=scratch_dir,
        min_criteria=min_criteria,
        max_criteria=max_criteria,
        shared_dir=shared_dir,
        agent_id="agent-1",
    )


def _read_runtime_guidance(codebase_path: str) -> str:
    """Read runtime guidance injected via `coral guide`.

    Guidance is stored in ``<shared_dir>/guidance/runtime.md``, or directly at
    ``.coral/public/guidance/runtime.md``.
    """
    if not codebase_path:
        return ""

    for shared_dir in [".claude", ".opencode"]:
        guidance_file = Path(codebase_path) / shared_dir / "guidance" / "runtime.md"
        if guidance_file.exists():
            try:
                content = guidance_file.read_text().strip()
                if content:
                    return content
            except OSError:
                pass

    coral_dir_file = Path(codebase_path) / ".coral_dir"
    if coral_dir_file.exists():
        try:
            coral_dir = Path(coral_dir_file.read_text().strip())
            guidance_file = coral_dir / "public" / "guidance" / "runtime.md"
            if guidance_file.exists():
                content = guidance_file.read_text().strip()
                if content:
                    return content
        except (OSError, ValueError):
            pass

    return ""


def _read_agent_notes(codebase_path: str) -> str:
    """Read agent notes from the worktree's shared notes directory."""
    if not codebase_path:
        return "No agent notes available."

    notes_dir = None
    for shared_dir in [".claude", ".opencode"]:
        candidate = Path(codebase_path) / shared_dir / "notes"
        if candidate.is_dir():
            notes_dir = candidate
            break

    if notes_dir is None:
        return "No agent notes available."

    note_files = sorted(notes_dir.glob("*.md"))
    if not note_files:
        return "No agent notes available."

    parts = []
    total_chars = 0
    for note_path in note_files:
        try:
            content = note_path.read_text()
        except OSError:
            continue

        if total_chars + len(content) > _MAX_AGENT_NOTES_CHARS:
            remaining = _MAX_AGENT_NOTES_CHARS - total_chars
            if remaining > 200:
                content = content[:remaining] + "\n\n[... truncated ...]"
            else:
                parts.append(f"\n[... {len(note_files) - len(parts)} more notes truncated ...]")
                break

        parts.append(f"### {note_path.name}\n\n{content}")
        total_chars += len(content)

    if not parts:
        return "No agent notes available."

    return (
        "The agent wrote the following notes about its findings and approach. "
        "Consider these when evolving the rubric — the agent may have discovered "
        "quality dimensions or concerns not yet captured in the criteria.\n\n"
        + "\n\n".join(parts)
    )


def _format_rubric(version: RubricVersion) -> str:
    """Format the current rubric version for inclusion in JUDGE.md."""
    lines = [f"**Rubric Version: v{version.version}**", ""]
    for i, r in enumerate(version.rubrics, 1):
        lines.append(f"{i}. **{r.name}** (weight: {r.weight})")
        lines.append(f"   {r.description}")
        lines.append("")

    if version.retired:
        lines.append("### Previously Retired")
        for r in version.retired:
            lines.append(f"- ~~{r.name}~~")
        lines.append("")

    return "\n".join(lines)


def _format_initial_rubric_instructions(config: CoralConfig) -> str:
    """Instructions for when no rubric exists yet (first evaluation)."""
    min_criteria = config.grader.args.get("min_criteria", 3)
    max_criteria = config.grader.args.get("max_criteria", 10)

    lines = [
        "**No rubric exists yet — this is the first evaluation.**",
        "",
        "You must generate an initial rubric before scoring. To do this:",
        "",
        "1. Read the agent's output files and the task description carefully.",
        f"2. Design {min_criteria} to {max_criteria} evaluation criteria that cover:",
        "   - Quality of reasoning and evidence (are claims supported? is analysis rigorous?)",
        "   - Completeness (does the output address all parts of the task?)",
        "   - Consideration of alternatives and counterarguments",
        "   - Presentation and readability",
        "",
        "   **Important:** Criteria should evaluate reasoning quality, not presuppose specific",
        "   conclusions. Use 'analyzes whether X' not 'explains why X'. The agent should be",
        "   rewarded for rigorous reasoning that engages with counterarguments, not for",
        "   reaching a particular answer.",
        "",
        "3. Assign weights reflecting relative importance (weights should roughly sum "
        f"to {max_criteria}).",
        "4. Score the output against your new criteria.",
        "",
        "Include the new criteria in `rubric_evolution.new_criteria` in your output.",
    ]

    return "\n".join(lines)


def _parse_guidance_into_criteria(runtime_guidance: str) -> list[dict[str, str]]:
    """Parse runtime guidance directives into locked criteria."""
    if not runtime_guidance:
        return []

    import re

    criteria = []
    for line in runtime_guidance.splitlines():
        line = line.strip()
        m = re.match(r"^-\s*\[.*?\]\s*(.+)$", line)
        if m:
            directive = m.group(1).strip()
            if directive:
                criteria.append(
                    {
                        "name": f"[USER] {directive[:80]}",
                        "description": directive,
                    }
                )
    return criteria


def _format_locked_criteria(criteria: list[dict[str, str]]) -> str:
    """Format locked criteria for inclusion in the rubric section."""
    lines = [
        "### Locked Criteria (from runtime guidance)",
        "",
        "The following criteria are **locked** — injected by the task supervisor. "
        "You MUST score each one as PASS or FAIL in `criteria_scores`. "
        "You CANNOT retire, rename, or modify these criteria. "
        "If the agent's output contradicts a locked criterion, it FAILS "
        "regardless of the quality of reasoning.",
        "",
    ]
    for i, c in enumerate(criteria, 1):
        lines.append(f"{i}. **{c['name']}** (weight: 3.0)")
        lines.append(f"   {c['description']}")
        lines.append("")

    return "\n".join(lines)
