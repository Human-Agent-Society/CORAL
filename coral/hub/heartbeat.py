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
}

# Which built-in actions default to global scope
DEFAULT_GLOBAL: dict[str, bool] = {
    "reflect": False,
    "consolidate": True,
    "pivot": False,
}

# Which built-in actions use plateau trigger instead of interval
DEFAULT_TRIGGER: dict[str, str] = {
    "reflect": "interval",
    "consolidate": "interval",
    "pivot": "plateau",
}

# Protected actions: reflect is always local, consolidate is always global
PROTECTED_LOCAL: set[str] = {"reflect"}
PROTECTED_GLOBAL: set[str] = {"consolidate"}
PROTECTED_ACTIONS: set[str] = PROTECTED_LOCAL | PROTECTED_GLOBAL

_GLOBAL_ID = "_global"


def _heartbeat_path(coral_dir: Path, agent_id: str) -> Path:
    return coral_dir / "public" / "heartbeat" / f"{agent_id}.json"


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

def read_agent_heartbeat(coral_dir: Path, agent_id: str) -> list[dict]:
    """Read local heartbeat actions for an agent."""
    return _read_actions(_heartbeat_path(coral_dir, agent_id))


def write_agent_heartbeat(coral_dir: Path, agent_id: str, actions: list[dict]) -> None:
    """Write local heartbeat actions for an agent.

    Protected local actions (reflect) are re-added if missing.
    """
    present = {a["name"] for a in actions}
    for name in PROTECTED_LOCAL:
        if name not in present:
            actions.append({
                "name": name,
                "every": 1,
                "prompt": DEFAULT_PROMPTS.get(name, ""),
            })
    _write_actions(_heartbeat_path(coral_dir, agent_id), actions)


# --- Global (shared across all agents) ---

def read_global_heartbeat(coral_dir: Path) -> list[dict]:
    """Read global heartbeat actions."""
    return _read_actions(_heartbeat_path(coral_dir, _GLOBAL_ID))


def write_global_heartbeat(coral_dir: Path, actions: list[dict]) -> None:
    """Write global heartbeat actions.

    Protected global actions (consolidate) are re-added if missing.
    """
    present = {a["name"] for a in actions}
    for name in PROTECTED_GLOBAL:
        if name not in present:
            actions.append({
                "name": name,
                "every": 10,
                "prompt": DEFAULT_PROMPTS.get(name, ""),
            })
    _write_actions(_heartbeat_path(coral_dir, _GLOBAL_ID), actions)


# --- Defaults from config ---

def default_local_actions(config) -> list[dict]:
    """Extract local actions from config's heartbeat list."""
    actions = []
    for action_cfg in config.agents.heartbeat:
        is_global = action_cfg.is_global or DEFAULT_GLOBAL.get(action_cfg.name, False)
        if not is_global:
            trigger = getattr(action_cfg, "trigger", None) or DEFAULT_TRIGGER.get(action_cfg.name, "interval")
            actions.append({
                "name": action_cfg.name,
                "every": action_cfg.every,
                "prompt": DEFAULT_PROMPTS.get(action_cfg.name, ""),
                "trigger": trigger,
            })
    return actions


def default_global_actions(config) -> list[dict]:
    """Extract global actions from config's heartbeat list."""
    actions = []
    for action_cfg in config.agents.heartbeat:
        is_global = action_cfg.is_global or DEFAULT_GLOBAL.get(action_cfg.name, False)
        if is_global:
            trigger = getattr(action_cfg, "trigger", None) or DEFAULT_TRIGGER.get(action_cfg.name, "interval")
            actions.append({
                "name": action_cfg.name,
                "every": action_cfg.every,
                "prompt": DEFAULT_PROMPTS.get(action_cfg.name, ""),
                "trigger": trigger,
            })
    return actions
