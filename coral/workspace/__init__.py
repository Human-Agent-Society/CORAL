"""Workspace setup for CORAL agents."""

from coral.workspace.project import (
    ProjectPaths,
    create_project,
    reconstruct_paths,
    seed_agent_role,
    slugify,
)
from coral.workspace.worktree import (
    apply_runtime_mounts,
    create_agent_worktree,
    get_coral_dir,
    repoint_shared_state,
    setup_claude_settings,
    setup_codex_settings,
    setup_cursor_settings,
    setup_gitignore,
    setup_opencode_settings,
    setup_shared_state,
    setup_worktree_env,
    write_agent_id,
    write_coral_dir,
)

__all__ = [
    "ProjectPaths",
    "apply_runtime_mounts",
    "create_agent_worktree",
    "create_project",
    "get_coral_dir",
    "reconstruct_paths",
    "repoint_shared_state",
    "seed_agent_role",
    "setup_claude_settings",
    "setup_codex_settings",
    "setup_cursor_settings",
    "setup_gitignore",
    "setup_opencode_settings",
    "setup_shared_state",
    "setup_worktree_env",
    "slugify",
    "write_agent_id",
    "write_coral_dir",
]
