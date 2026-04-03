"""Workspace setup for CORAL agents."""

from coral.workspace.project import (
    ProjectPaths,
    create_project,
    reconstruct_paths,
    slugify,
)
from coral.workspace.worktree import (
    create_agent_worktree,
    get_coral_dir,
    setup_claude_settings,
    setup_codex_settings,
    setup_opencode_settings,
    setup_gitignore,
    setup_shared_state,
    setup_worktree_env,
    write_agent_id,
    write_coral_dir,
)

__all__ = [
    "ProjectPaths",
    "create_agent_worktree",
    "create_project",
    "get_coral_dir",
    "reconstruct_paths",
    "setup_claude_settings",
    "setup_codex_settings",
    "setup_opencode_settings",
    "setup_gitignore",
    "setup_shared_state",
    "setup_worktree_env",
    "slugify",
    "write_agent_id",
    "write_coral_dir",
]
