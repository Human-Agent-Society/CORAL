"""Generate CORAL.md agent instructions from template."""

from __future__ import annotations

from pathlib import Path

from coral.config import CoralConfig

_TEMPLATE_PATH = Path(__file__).parent / "coral.md.template"
_SINGLE_TEMPLATE_PATH = Path(__file__).parent / "coral_single.md.template"
_RUBRIC_TEMPLATE_PATH = Path(__file__).parent / "coral_rubric.md.template"
_RUBRIC_SINGLE_TEMPLATE_PATH = Path(__file__).parent / "coral_rubric_single.md.template"


def generate_coral_md(
    config: CoralConfig,
    agent_id: str,
    single_agent: bool = False,
    shared_dir: str = ".claude",
) -> str:
    """Produce the CORAL.md file that agents read at startup.

    Args:
        config: The coral config
        agent_id: This agent's ID
        single_agent: If True, use simplified single-agent template (no sharing references)
        shared_dir: Name of the shared state directory (e.g. ".claude", ".codex", ".opencode")
    """
    is_dynamic_rubric = config.grader.type in ("dynamic_rubric_judge", "agent_judge")
    has_rubrics = bool(config.task.rubrics) or is_dynamic_rubric
    if has_rubrics:
        template_path = _RUBRIC_SINGLE_TEMPLATE_PATH if single_agent else _RUBRIC_TEMPLATE_PATH
    else:
        template_path = _SINGLE_TEMPLATE_PATH if single_agent else _TEMPLATE_PATH
    template = template_path.read_text()

    # Build optional sections
    tips_section = ""
    if config.task.tips:
        tips_section = f"\n## Tips\n{config.task.tips}\n"

    # Determine score direction from config or grader type
    score_direction = _get_score_direction(config)

    # Research step is conditional
    research_enabled = config.agents.research
    if research_enabled:
        workflow_summary = "research → plan → edit → eval → repeat"
        research_section = (
            "\n## 1. Research\n\n"
            "**On your first iteration and whenever you're changing direction**, "
            "invest time in research before planning.\n\n"
            "- **Search for techniques and algorithms** relevant to the task. "
            "Use web search to find state-of-the-art approaches, academic papers, "
            "blog posts, or forum discussions that address similar problems.\n"
            "- **Look for code examples** or reference implementations of similar "
            "problems. Understanding how others solved related challenges can save "
            "significant effort.\n"
            "- **Review relevant documentation** for libraries, APIs, or "
            "architectures you might use.\n\n"
            "**When to research:**\n"
            "- First iteration: always. Understand the landscape before writing code.\n"
            "- After getting stuck (3+ evals without improvement): step back and "
            "look for new angles.\n"
            "- When pivoting to a fundamentally different approach.\n\n"
            "**When to skip:** If you have a clear plan from your last eval's feedback "
            "and just need to iterate on an existing approach, go straight to Step 2.\n"
        )
        step_offset = 2  # Plan starts at step 2
        research_back_reference = " (or **Step 1: Research** if you need a new direction)"
        repeat_research_hint = (
            "go back to **Step 1: Research** to find new techniques via web search, "
        )
    else:
        workflow_summary = "plan → edit → eval → repeat"
        research_section = ""
        step_offset = 1  # Plan starts at step 1
        research_back_reference = ""
        repeat_research_hint = "research new techniques, "

    # Build rubrics section for rubric templates
    rubrics_section = ""
    if has_rubrics:
        rubrics_lines = []
        for i, r in enumerate(config.task.rubrics, 1):
            rubrics_lines.append(f"{i}. **{r.name}** (weight: {r.weight}): {r.description}")
        rubrics_section = "\n".join(rubrics_lines)
        if is_dynamic_rubric:
            dynamic_note = (
                "\n\n> **Dynamic Rubrics:** This task uses auto-generated evaluation criteria "
                "that evolve over time. Check `{shared_dir}/rubrics/current.md` for the active "
                "rubric and version. Your rubric version is shown in each eval result."
            ).format(shared_dir=shared_dir)
            rubrics_section = (rubrics_section + dynamic_note) if rubrics_section else dynamic_note

    # Eval timeout: grader timeout + buffer for git operations
    grader_timeout = config.grader.timeout or 300
    eval_timeout = grader_timeout + 60  # extra margin for commit + overhead

    format_kwargs = dict(
        task_name=config.task.name,
        task_description=config.task.description,
        tips_section=tips_section,
        score_direction=score_direction,
        agent_id=agent_id,
        shared_dir=shared_dir,
        workflow_summary=workflow_summary,
        research_section=research_section,
        plan_step_num=step_offset,
        edit_step_num=step_offset + 1,
        eval_step_num=step_offset + 2,
        results_step_num=step_offset + 3,
        knowledge_step_num=step_offset + 4,
        research_back_reference=research_back_reference,
        repeat_research_hint=repeat_research_hint,
        eval_timeout=eval_timeout,
    )

    if has_rubrics:
        format_kwargs["rubrics_section"] = rubrics_section

    return template.format(**format_kwargs)


def _get_score_direction(config: CoralConfig) -> str:
    """Return a human-readable description of what 'better' means for this grader."""
    # Type-specific descriptions for builtin graders
    if config.grader.type:
        type_directions = {
            "kernel_builder": "lower cycle count is better (score 0-1, higher = faster kernel)",
            "swebench": "higher is better (pass rate across tasks, 0-1)",
            "terminalbench": "higher is better (pass rate across tasks, 0-1)",
            "erdos": "higher is better (score = benchmark/c5_bound, >1.0 means new record)",
            "spaceship_titanic": "higher is better (classification accuracy, 0-1 scale; 0.50 = naive, 0.80+ = strong)",
            "function": "higher is better (0-1 scale) unless the task description says otherwise",
            "kernel_engineering": "higher is better (1000/runtime_us — lower kernel runtime = higher score)",
        }
        if config.grader.type in type_directions:
            return type_directions[config.grader.type]

    # Use direction from config
    if config.grader.direction == "minimize":
        return "lower is better"
    return "higher is better"
