"""PreToolUse hook: restrict file operations to the agent's own worktree.

Ensures each agent can only read/edit/write files within its own worktree
and the shared .coral/public/ directory.  Read-only tools (Read, Glob, Grep)
may also access sibling agent worktrees.  .coral/private/ is always off-limits.
Uses the .coral_dir breadcrumb file to locate shared state.

Also guards the Bash tool by scanning commands for absolute paths that point
outside the allowed roots.

Pass --research to allow WebSearch and WebFetch tools (disabled by default).

Exit codes (Claude Code hook protocol):
  0 — allow the tool call
  2 — block the tool call (stderr is shown to the agent as the reason)
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

# Tools that take a file/directory path we should guard.
_FILE_TOOLS = {
    "Read": "file_path",
    "Edit": "file_path",
    "Write": "file_path",
}

_DIR_TOOLS = {
    "Glob": "path",
    "Grep": "path",
}

# Regex to find absolute paths in a bash command string.
_ABS_PATH_RE = re.compile(r'(?<!\w)/(?:Users|home|tmp|var|etc|opt|usr|private)(?:/\S*)')


def _resolve(path_str: str, cwd: Path) -> Path:
    """Resolve a path, treating relative paths as relative to cwd."""
    p = Path(path_str)
    if not p.is_absolute():
        p = cwd / p
    return p.resolve()


def _is_under(path: Path, parent: Path) -> bool:
    """Check if *path* is equal to or a descendant of *parent*."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _get_allowed_roots(cwd: Path) -> tuple[Path, Path | None, Path | None, Path | None]:
    """Return (worktree, coral_public, coral_private, agents_dir) for the given cwd."""
    worktree = cwd
    agents_dir = worktree.parent  # e.g. run_dir/agents/

    coral_public: Path | None = None
    coral_private: Path | None = None
    coral_dir_file = cwd / ".coral_dir"
    if coral_dir_file.exists():
        try:
            coral_dir = Path(coral_dir_file.read_text().strip()).resolve()
            coral_public = coral_dir / "public"
            coral_private = coral_dir / "private"
        except (OSError, ValueError):
            pass

    return worktree, coral_public, coral_private, agents_dir


def _check_path_allowed(
    resolved: Path,
    worktree: Path,
    coral_public: Path | None,
    coral_private: Path | None,
    agents_dir: Path | None = None,
    read_only: bool = False,
) -> str | None:
    """Return an error message if *resolved* is disallowed, else None."""
    if coral_private and _is_under(resolved, coral_private):
        return f"cannot access .coral/private/ (path: {resolved})"
    if _is_under(resolved, worktree):
        return None
    if coral_public and _is_under(resolved, coral_public):
        return None
    # Read-only tools may access sibling agent worktrees
    if read_only and agents_dir and _is_under(resolved, agents_dir):
        return None
    return (
        f"path is outside your workspace. "
        f"You may only access files within your worktree ({worktree}) "
        f"and the shared .coral/public/ directory. "
        f"Requested path: {resolved}"
    )


def _check_bash_command(command: str, cwd: Path, worktree: Path,
                        coral_public: Path | None, coral_private: Path | None) -> str | None:
    """Scan a bash command string for paths outside allowed roots.

    Returns an error message if a disallowed path is found, else None.
    """
    # Extract absolute paths from the command
    abs_paths = _ABS_PATH_RE.findall(command)

    # Also try to extract paths from shell-parsed tokens
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    for token in tokens:
        if token.startswith("/") and not token.startswith("//"):
            abs_paths.append(token)

    # Deduplicate
    seen: set[str] = set()
    for raw_path in abs_paths:
        # Strip trailing punctuation that might be part of shell syntax
        raw_path = raw_path.rstrip(";|&>)")
        if not raw_path or raw_path in seen:
            continue
        seen.add(raw_path)

        try:
            resolved = Path(raw_path).resolve()
        except (OSError, ValueError):
            continue

        err = _check_path_allowed(resolved, worktree, coral_public, coral_private)
        if err is not None:
            return err

    return None


def main() -> None:
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        # Can't parse input — allow by default to avoid blocking agents.
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})
    cwd = Path(hook_input.get("cwd", ".")).resolve()

    worktree, coral_public, coral_private, agents_dir = _get_allowed_roots(cwd)

    # --- Block denied tools (--dangerously-skip-permissions bypasses settings) ---
    research_mode = "--research" in sys.argv
    if not research_mode and tool_name in {"WebSearch", "WebFetch"}:
        print(f"Blocked: {tool_name} is not allowed for agents.", file=sys.stderr)
        sys.exit(2)

    # --- Guard Bash tool ---
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        err = _check_bash_command(command, cwd, worktree, coral_public, coral_private)
        if err is not None:
            print(f"Blocked: Bash {err}", file=sys.stderr)
            sys.exit(2)
        sys.exit(0)

    # --- Guard file/directory tools ---
    is_read_only = tool_name in _DIR_TOOLS or tool_name == "Read"
    path_key = _FILE_TOOLS.get(tool_name) or _DIR_TOOLS.get(tool_name)
    if path_key is None:
        # Not a file tool — allow.
        sys.exit(0)

    raw_path = tool_input.get(path_key)
    if raw_path is None:
        # Glob/Grep without an explicit path default to cwd — allow.
        sys.exit(0)

    resolved = _resolve(raw_path, cwd)

    err = _check_path_allowed(resolved, worktree, coral_public, coral_private,
                              agents_dir=agents_dir, read_only=is_read_only)
    if err is not None:
        print(f"Blocked: {tool_name} {err}", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
