"""UserPromptSubmit hook: periodically remind agents to document skills."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def check_and_remind(coral_dir: Path) -> str | None:
    """Check state and return a skill reflection prompt every 2 evals."""
    # Read eval count
    counter_file = coral_dir / "public" / "eval_count"
    if not counter_file.exists():
        return None
    try:
        eval_count = int(counter_file.read_text().strip())
    except (ValueError, OSError):
        return None

    # Every 2 evals, prompt the agent to write/update skills
    if eval_count % 2 != 0:
        return None

    return (
        f"You've completed {eval_count} evals. You MUST create or update a skill now. "
        f"Follow the workflow in `.claude/skills/skill-creator/SKILL.md` to create, "
        f"test, and optimize your skill. Any technique, optimization approach, or workflow you "
        f"used belongs in a skill. Update an existing skill if one covers the same topic."
    )


def main() -> None:
    """Entry point for UserPromptSubmit hook.

    Reads hook input JSON from stdin, checks skill state, and optionally
    outputs a reminder via hookSpecificOutput.additionalContext.
    """
    # Read hook input from stdin (Claude Code hook protocol)
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        hook_input = {}

    cwd = Path(hook_input.get("cwd", ".")).resolve()

    # Derive .coral directory from .coral_dir breadcrumb file
    coral_dir = None
    coral_dir_file = cwd / ".coral_dir"
    if coral_dir_file.exists():
        try:
            coral_dir = Path(coral_dir_file.read_text().strip()).resolve()
        except (OSError, ValueError):
            pass

    if coral_dir is None:
        sys.exit(0)

    reminder = check_and_remind(coral_dir)
    if reminder:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": reminder,
            }
        }
        print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()
