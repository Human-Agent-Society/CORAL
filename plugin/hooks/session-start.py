#!/usr/bin/env python3
"""CORAL plugin SessionStart hook.

Two jobs, both cheap and dependency-free:
  1. Detect whether the `coral` CLI is installed and reachable on PATH.
  2. Inject a small block of context so the agent knows CORAL is available
     and which skill to reach for (authoring vs. running tasks).

Output contract (Claude Code SessionStart hook):
  print a JSON object on stdout with
  hookSpecificOutput.additionalContext — that string is added to the
  session context. We never block the session (exit 0 always).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys


def _coral_version(coral_path: str) -> str | None:
    """Best-effort `coral --version`; None if it doesn't answer quickly."""
    for args in (["--version"], ["version"]):
        try:
            out = subprocess.run(
                [coral_path, *args],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        if out.returncode == 0:
            return (out.stdout or out.stderr).strip() or None
    return None


def _installed_context(version: str | None) -> str:
    ver = f" ({version})" if version else ""
    return (
        f"# CORAL is available\n\n"
        f"The `coral` CLI is installed{ver}. CORAL runs autonomous coding agents "
        f"against a grader and a leaderboard.\n\n"
        f"When the user wants to **author a task** (a `task.yaml` + `seed/` + grader "
        f"package), use the `creating-a-coral-task` skill. When they want to **run or "
        f"manage experiments** (`coral start / status / resume / log / show / stop`), "
        f"use the `running-coral-experiments` skill. For install / what-is-coral / "
        f"when-to-use, see `coral-quickstart`.\n\n"
        f"Don't memorize flags — run `coral --help` or `coral <cmd> --help`, and let "
        f"the skills drive the workflow.\n"
    )


def _missing_context() -> str:
    return (
        "# CORAL CLI not found\n\n"
        "The `coral` CLI is not on PATH. If the user asks to author or run a CORAL "
        "task, install it first:\n\n"
        "```bash\n"
        "curl -fsSL https://raw.githubusercontent.com/Human-Agent-Society/CORAL/main/install.sh | sh\n"
        "# or, with uv:\n"
        "uv tool install coral\n"
        "```\n\n"
        "Then the `creating-a-coral-task` and `running-coral-experiments` skills apply. "
        "Docs: https://docs.coralxyz.com/\n"
    )


def main() -> int:
    coral_path = shutil.which("coral")
    if coral_path:
        context = _installed_context(_coral_version(coral_path))
    else:
        context = _missing_context()

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
