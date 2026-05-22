"""Generate CORAL.md agent instructions from template."""

from __future__ import annotations

from pathlib import Path

from coral.config import CoralConfig

_TEMPLATE_PATH = Path(__file__).parent / "coral.md.template"
_SINGLE_TEMPLATE_PATH = Path(__file__).parent / "coral_single.md.template"


def generate_coral_md(
    config: CoralConfig,
    agent_id: str,
    single_agent: bool = False,
    shared_dir: str = ".claude",
    coral_dir: Path | None = None,
) -> str:
    """Produce the CORAL.md file that agents read at startup.

    Args:
        config: The coral config
        agent_id: This agent's ID
        single_agent: If True, use simplified single-agent template (no sharing references)
        shared_dir: Name of the shared state directory (e.g. ".claude", ".codex", ".opencode")
        coral_dir: Path to ``.coral/`` for rendering the team falsification
            section. When None the section is empty (used by tests and by
            very-early renders before the directory exists).
    """
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
            "invest time in deep research before planning. "
            f"Read the `deep-research` skill (`{shared_dir}/skills/deep-research/SKILL.md`) "
            "for a structured research workflow.\n\n"
            "**Research steps:**\n"
            "- **Understand the problem deeply** — read the grader code, understand the "
            "objective function, identify constraints and evaluation criteria.\n"
            "- **Survey the literature** — use web search to find state-of-the-art approaches, "
            "academic papers, benchmark comparisons, and existing implementations. "
            'Search broadly first (`"[problem] state of the art"`), then drill into '
            "specific techniques.\n"
            "- **Review domain knowledge** — if the task involves specialized domains "
            "(biology, chemistry, physics, math), research the underlying science. "
            "Understanding the domain often reveals approaches that pure ML/CS thinking misses.\n"
            "- **Analyze existing solutions** — check shared notes, past attempts, and "
            "what has been tried before. Build on what's known.\n"
            "- **Compare 2-4 candidate approaches** — document trade-offs, evidence, "
            "and implementation complexity for each.\n"
            f"- **Write a research summary** — save findings to `{shared_dir}/notes/research-[topic].md` "
            f"so all agents benefit. See `{shared_dir}/skills/deep-research/references/` "
            "for templates.\n\n"
            "**When to research:**\n"
            "- First iteration: always. Understand the landscape before writing code.\n"
            "- After getting stuck (3+ evals without improvement): step back and "
            "look for new angles.\n"
            "- When pivoting to a fundamentally different approach.\n"
            "- When the task involves unfamiliar domain knowledge.\n\n"
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

    return template.format(
        task_name=config.task.name,
        task_description=config.task.description,
        tips_section=tips_section,
        score_direction=score_direction,
        agent_id=agent_id,
        shared_dir=shared_dir,
        workflow_summary=workflow_summary,
        research_section=research_section,
        falsifications_section=_render_falsifications_section(config, coral_dir),
        plan_step_num=step_offset,
        edit_step_num=step_offset + 1,
        eval_step_num=step_offset + 2,
        results_step_num=step_offset + 3,
        knowledge_step_num=step_offset + 4,
        research_back_reference=research_back_reference,
        repeat_research_hint=repeat_research_hint,
    )


def _get_score_direction(config: CoralConfig) -> str:
    """Return a human-readable description of what 'better' means for this grader."""
    if config.grader.direction == "minimize":
        return "lower is better"
    return "higher is better"


def _render_falsifications_section(config: CoralConfig, coral_dir: Path | None) -> str:
    """Render the "Team falsification ledger" CORAL.md section.

    Returns the empty string when there's nothing to show — so existing
    runs / tests / single-agent setups don't grow a noisy blank header.
    """
    if coral_dir is None or not Path(coral_dir).exists():
        return ""

    # Lazy import: avoid circular dep at module load (template imported by
    # other startup paths).
    from coral.hub.attempts import read_eval_count
    from coral.hub.falsifications import list_topics

    sharing = config.sharing
    # sharing.falsification.{quorum,ttl_evals} (FalsificationConfig sub-config)
    falsification = getattr(sharing, "falsification", None)
    quorum = max(1, int(getattr(falsification, "quorum", 2) or 2))
    default_ttl = max(1, int(getattr(falsification, "ttl_evals", 30) or 30))
    current_eval = read_eval_count(coral_dir)

    try:
        statuses = list_topics(
            coral_dir,
            current_eval=current_eval,
            quorum=quorum,
            default_ttl=default_ttl,
        )
    except Exception:
        # Defensive: a broken note shouldn't prevent agent startup.
        return ""

    consensus = [s for s in statuses if s.level == "consensus"]
    disputed = [s for s in statuses if s.level in ("disputed", "stale")]

    # Always render the section header so agents discover the CLI commands
    # (`coral falsify` / `coral falsified` / `coral disputed`) — even when
    # the ledger is empty. Otherwise agents who never see a populated
    # ledger never learn the mechanism exists.

    lines: list[str] = ["", "## Team falsification ledger"]
    lines.append(
        f"\nA topic counts as **team consensus** only after {quorum} distinct "
        f"agents have independently claimed it dead within the last "
        f"{default_ttl} evals. A lone claim is **disputed** until a second "
        "agent confirms it, and any claim expires past TTL to **stale**.\n"
        "Vote (only after a real failed eval): "
        "`coral falsify <slug> -m \"evidence\"`. "
        "Inspect: `coral falsified` / `coral disputed`. "
        "If the team has marked something disputed/stale, treat it as a "
        "*hypothesis worth re-testing*, not a confirmed dead-end."
    )

    if consensus:
        lines.append("\n### Consensus (don't waste evals here without new evidence)")
        for s in consensus:
            voices = ", ".join(s.voices)
            lines.append(f"- **{s.topic}** — confirmed by: {voices}")

    if disputed:
        lines.append("\n### Disputed / stale (single voice or expired — worth re-testing)")
        for s in disputed:
            if s.level == "stale":
                tag = "stale (all claims expired)"
            else:
                remaining = max(0, s.expires_at_eval - current_eval)
                tag = f"disputed (1/{quorum}, expires in {remaining} evals)"
            voices = ", ".join(s.all_voices) or "—"
            lines.append(f"- **{s.topic}** — {tag}; claimed by: {voices}")

    if not consensus and not disputed:
        lines.append(
            "\n*No falsification claims yet. Be the first to vote when you "
            "have evidence a topic is dead.*"
        )

    lines.append("")  # trailing newline for clean section spacing
    return "\n".join(lines)
