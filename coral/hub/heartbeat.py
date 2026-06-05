"""Per-agent and global heartbeat configuration CRUD.

Local actions:  `.coral/public/heartbeat/<agent-id>.json`
Global actions: `.coral/public/heartbeat/_global.json`

The manager merges both when building a heartbeat runner for an agent.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from coral.hub._island import island_root

logger = logging.getLogger(__name__)

# Load prompt templates from markdown files
_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_file = _PROMPTS_DIR / f"{name}.md"
    if prompt_file.exists():
        return prompt_file.read_text()
    return ""


# Prompt templates use {shared_dir} which is resolved at runtime to the
# agent's shared directory (`.claude/` for Claude Code, `.codex/` for Codex,
# `.opencode/` for OpenCode).
DEFAULT_PROMPTS: dict[str, str] = {
    "reflect": _load_prompt("reflect"),
    "consolidate": _load_prompt("consolidate"),
    "pivot": _load_prompt("pivot"),
    "lint_wiki": _load_prompt("lint_wiki"),
}

# Which built-in actions default to global scope
DEFAULT_GLOBAL: dict[str, bool] = {
    "reflect": False,
    "consolidate": True,
    "pivot": False,
    "lint_wiki": True,
}

# Which built-in actions use plateau trigger instead of interval
DEFAULT_TRIGGER: dict[str, str] = {
    "reflect": "interval",
    "consolidate": "interval",
    "pivot": "plateau",
    "lint_wiki": "interval",
}

# Protected actions: reflect is always local, consolidate is always global
PROTECTED_LOCAL: set[str] = {"reflect"}
PROTECTED_GLOBAL: set[str] = {"consolidate"}
PROTECTED_ACTIONS: set[str] = PROTECTED_LOCAL | PROTECTED_GLOBAL

_GLOBAL_ID = "_global"


def _heartbeat_path(
    coral_dir: Path,
    agent_id: str,
    island_id: str | int | None = None,
) -> Path:
    return island_root(coral_dir, island_id) / "heartbeat" / f"{agent_id}.json"


def _require_write_scope(coral_dir: Path, island_id: str | int | None) -> None:
    if island_id is None and (coral_dir / "islands").exists():
        raise ValueError(
            "island_id is required when writing heartbeat config in a multi-island run"
        )


def _read_actions(path: Path) -> list[dict]:
    """Read actions from a heartbeat JSON file."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data.get("actions", [])
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read heartbeat config {path.name}: {e}")
        return []


def _write_actions(path: Path, actions: list[dict]) -> None:
    """Write actions to a heartbeat JSON file (atomic)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps({"actions": actions}, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        os.write(fd, content.encode())
        os.close(fd)
        fd = -1
        os.replace(tmp, str(path))
    except Exception:
        if fd >= 0:
            os.close(fd)
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# --- Local (per-agent) ---


def read_agent_heartbeat(
    coral_dir: Path,
    agent_id: str,
    island_id: str | int | None = None,
) -> list[dict]:
    """Read local heartbeat actions for an agent.

    Routing rules in multi-island mode (``coral_dir/islands/`` exists):
    - If ``island_id`` is provided, read only that island.
    - If ``island_id`` is omitted, fan out across every island and merge
      matches. The prefix in ids like ``0-agent-1`` is birth lineage, not
      current location after migration.
    """
    coral_dir = Path(coral_dir)
    if island_id is not None or not (coral_dir / "islands").exists():
        return _read_actions(_heartbeat_path(coral_dir, agent_id, island_id))

    from coral.hub._island import all_view_roots

    merged: list[dict] = []
    seen: set[tuple] = set()
    for view_root in all_view_roots(coral_dir):
        for action in _read_actions(_heartbeat_path(coral_dir, agent_id, island_id=view_root.name)):
            key = (action.get("name"), action.get("every"), action.get("trigger"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(action)
    return merged


def write_agent_heartbeat(
    coral_dir: Path,
    agent_id: str,
    actions: list[dict],
    island_id: str | int | None = None,
) -> None:
    """Write local heartbeat actions for an agent.

    Protected local actions (reflect) are re-added if missing.
    """
    coral_dir = Path(coral_dir)
    _require_write_scope(coral_dir, island_id)
    present = {a["name"] for a in actions}
    for name in PROTECTED_LOCAL:
        if name not in present:
            actions.append(
                {
                    "name": name,
                    "every": 1,
                    "prompt": DEFAULT_PROMPTS.get(name, ""),
                }
            )
    _write_actions(_heartbeat_path(coral_dir, agent_id, island_id), actions)


# --- Global (shared across all agents) ---


def read_global_heartbeat(
    coral_dir: Path,
    island_id: str | int | None = None,
) -> list[dict]:
    """Read global heartbeat actions.

    With ``island_id=None`` in multi-island mode, merges global heartbeats
    across every island (deduped by action name) so a per-island override
    on one island doesn't shadow the others.
    """
    coral_dir = Path(coral_dir)
    if island_id is not None or not (coral_dir / "islands").exists():
        return _read_actions(_heartbeat_path(coral_dir, _GLOBAL_ID, island_id))

    from coral.hub._island import all_view_roots

    merged: list[dict] = []
    seen: set[tuple] = set()
    for view_root in all_view_roots(coral_dir):
        for action in _read_actions(
            _heartbeat_path(coral_dir, _GLOBAL_ID, island_id=view_root.name)
        ):
            # Dedup by (name, every, trigger) so identical defaults across
            # islands collapse; distinct per-island overrides still surface.
            key = (
                action.get("name"),
                action.get("every"),
                action.get("trigger"),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(action)
    return merged


def write_global_heartbeat(
    coral_dir: Path,
    actions: list[dict],
    island_id: str | int | None = None,
) -> None:
    """Write global heartbeat actions.

    Protected global actions (consolidate) are re-added if missing.
    """
    coral_dir = Path(coral_dir)
    _require_write_scope(coral_dir, island_id)
    present = {a["name"] for a in actions}
    for name in PROTECTED_GLOBAL:
        if name not in present:
            actions.append(
                {
                    "name": name,
                    "every": 10,
                    "prompt": DEFAULT_PROMPTS.get(name, ""),
                }
            )
    _write_actions(_heartbeat_path(coral_dir, _GLOBAL_ID, island_id), actions)


# --- Defaults from config ---


def default_local_actions(config) -> list[dict]:
    """Extract local actions from config's heartbeat list."""
    actions = []
    for action_cfg in config.agents.heartbeat:
        is_global = action_cfg.is_global or DEFAULT_GLOBAL.get(action_cfg.name, False)
        if not is_global:
            trigger = getattr(action_cfg, "trigger", None) or DEFAULT_TRIGGER.get(
                action_cfg.name, "interval"
            )
            actions.append(
                {
                    "name": action_cfg.name,
                    "every": action_cfg.every,
                    "prompt": action_cfg.prompt or DEFAULT_PROMPTS.get(action_cfg.name, ""),
                    "trigger": trigger,
                    "options": dict(getattr(action_cfg, "options", {}) or {}),
                }
            )
    return actions


def default_global_actions(config) -> list[dict]:
    """Extract global actions from config's heartbeat list."""
    actions = []
    for action_cfg in config.agents.heartbeat:
        is_global = action_cfg.is_global or DEFAULT_GLOBAL.get(action_cfg.name, False)
        if is_global:
            trigger = getattr(action_cfg, "trigger", None) or DEFAULT_TRIGGER.get(
                action_cfg.name, "interval"
            )
            actions.append(
                {
                    "name": action_cfg.name,
                    "every": action_cfg.every,
                    "prompt": action_cfg.prompt or DEFAULT_PROMPTS.get(action_cfg.name, ""),
                    "trigger": trigger,
                    "options": dict(getattr(action_cfg, "options", {}) or {}),
                }
            )
    return actions
