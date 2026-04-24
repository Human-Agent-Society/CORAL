"""Warm-start: optional research phase before the main coding loop."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from coral.agent.runtime import AgentHandle
from coral.config import CoralConfig

logger = logging.getLogger(__name__)

# Load prompt template from markdown file (same location as heartbeat prompts)
_PROMPTS_DIR = Path(__file__).parent.parent / "hub" / "prompts"


def _load_prompt(name: str) -> str:
    prompt_file = _PROMPTS_DIR / f"{name}.md"
    if prompt_file.exists():
        return prompt_file.read_text()
    return ""


RESEARCH_PROMPT_TEMPLATE = _load_prompt("warmstart_research")


class WarmStartRunner:
    """Orchestrate the warm-start research phase.

    Usage from AgentManager:
        runner = WarmStartRunner(config, shared_dir_name)
        if runner.enabled:
            # spawn agents with runner.research_prompt(), wait, collect sessions
        prompt = runner.main_prompt()
    """

    def __init__(self, config: CoralConfig, shared_dir: str = ".claude") -> None:
        self.config = config
        self.shared_dir = shared_dir
        self.ws = config.agents.warmstart

    @property
    def enabled(self) -> bool:
        return self.ws.enabled

    def research_prompt(self) -> str:
        """Return the research-phase prompt, formatted with the agent's shared dir."""
        if RESEARCH_PROMPT_TEMPLATE:
            return RESEARCH_PROMPT_TEMPLATE.format(shared_dir=self.shared_dir)
        # Fallback if template file is missing
        return (
            "Research the task thoroughly using web search. "
            f"Write findings to `{self.shared_dir}/notes/`. "
            "Do NOT run `coral eval` or write code."
        )

    def main_prompt(self) -> str:
        """Return the prompt for the main coding phase after research."""
        return f"Begin. Review the research notes in `{self.shared_dir}/notes/` before coding."

    def wait_for_research(self, handles: list[AgentHandle], poll_interval: int = 3) -> None:
        """Block until all research-phase agents have exited."""
        logger.info(f"Warm-start: waiting for {len(handles)} agent(s) to finish research...")
        while any(h.alive for h in handles):
            time.sleep(poll_interval)
        logger.info("Warm-start: research phase complete.")
