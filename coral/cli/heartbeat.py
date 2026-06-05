"""Commands: heartbeat show/set/remove/reset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from coral.cli._helpers import find_coral_dir_and_island, read_agent_id


def cmd_heartbeat(args: argparse.Namespace) -> None:
    """Show or modify per-agent heartbeat configuration."""
    sub = getattr(args, "heartbeat_command", None)
    if sub == "set":
        _cmd_heartbeat_set(args)
    elif sub == "remove":
        _cmd_heartbeat_remove(args)
    elif sub == "reset":
        _cmd_heartbeat_reset(args)
    else:
        _cmd_heartbeat_show(args)


def _require_heartbeat_write_scope(coral_dir, island_id: str | int | None) -> None:
    """Reject ambiguous heartbeat mutations from aggregate multi-island views."""
    coral_dir = Path(coral_dir)
    if island_id is None and (coral_dir / "islands").exists():
        print(
            "Error: heartbeat changes in a multi-island run must be made from "
            "an agent worktree with a valid .coral_island breadcrumb.",
            file=sys.stderr,
        )
        sys.exit(1)


def _cmd_heartbeat_show(args: argparse.Namespace) -> None:
    """Show current heartbeat config: local actions + global actions."""
    from coral.hub.heartbeat import (
        PROTECTED_ACTIONS,
        read_agent_heartbeat,
        read_global_heartbeat,
    )

    coral_dir, island_id = find_coral_dir_and_island(
        getattr(args, "task", None),
        getattr(args, "run", None),
    )
    agent_id = read_agent_id()

    local_actions = read_agent_heartbeat(coral_dir, agent_id, island_id=island_id)
    global_actions = read_global_heartbeat(coral_dir, island_id=island_id)

    if not local_actions and not global_actions:
        print(f"No heartbeat config found for {agent_id}.")
        return

    print(f"Heartbeat config for {agent_id}:")
    if local_actions:
        print()
        print("  Local (per-agent eval count):")
        for action in local_actions:
            name = action["name"]
            every = action.get("every", 1)
            trigger = action.get("trigger", "interval")
            protected = " (protected)" if name in PROTECTED_ACTIONS else ""
            if trigger == "plateau":
                print(f"    {name}: after {every} non-improving eval(s) [plateau]{protected}")
            else:
                print(f"    {name}: every {every} eval(s){protected}")
    if global_actions:
        print()
        print("  Global (shared eval count, all agents):")
        for action in global_actions:
            name = action["name"]
            every = action.get("every", 1)
            trigger = action.get("trigger", "interval")
            protected = " (protected)" if name in PROTECTED_ACTIONS else ""
            if trigger == "plateau":
                print(f"    {name}: after {every} non-improving eval(s) [plateau]{protected}")
            else:
                print(f"    {name}: every {every} eval(s){protected}")


def _cmd_heartbeat_set(args: argparse.Namespace) -> None:
    """Add or update a heartbeat action."""
    from coral.hub.heartbeat import (
        DEFAULT_GLOBAL,
        DEFAULT_PROMPTS,
        DEFAULT_TRIGGER,
        PROTECTED_GLOBAL,
        PROTECTED_LOCAL,
        read_agent_heartbeat,
        read_global_heartbeat,
        write_agent_heartbeat,
        write_global_heartbeat,
    )

    coral_dir, island_id = find_coral_dir_and_island(
        getattr(args, "task", None),
        getattr(args, "run", None),
    )
    _require_heartbeat_write_scope(coral_dir, island_id)
    agent_id = read_agent_id()
    name = args.name
    every = args.every
    prompt = getattr(args, "prompt", None)
    is_global = getattr(args, "is_global", None)
    trigger = getattr(args, "trigger", None)
    epsilon = getattr(args, "epsilon", None)

    if every <= 0:
        print("Error: --every must be at least 1.", file=sys.stderr)
        sys.exit(1)

    if epsilon is not None and epsilon < 0:
        print("Error: --epsilon must be >= 0.", file=sys.stderr)
        sys.exit(1)

    # For custom (non-built-in) names, --prompt is required
    if name not in DEFAULT_PROMPTS and not prompt:
        print(
            f"Error: --prompt is required for custom action '{name}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Protected actions can't switch scope
    if name in PROTECTED_LOCAL and is_global:
        print(f"Error: '{name}' is a protected local action.", file=sys.stderr)
        sys.exit(1)
    if name in PROTECTED_GLOBAL and is_global is False:
        print(f"Error: '{name}' is a protected global action.", file=sys.stderr)
        sys.exit(1)

    # Determine scope: explicit flag > existing location > built-in default
    if is_global is None:
        # Check if action already exists in either file
        global_actions = read_global_heartbeat(coral_dir, island_id=island_id)
        if any(a["name"] == name for a in global_actions):
            is_global = True
        else:
            is_global = DEFAULT_GLOBAL.get(name, False)

    # Resolve trigger: explicit flag > existing > built-in default
    if trigger is None:
        trigger = DEFAULT_TRIGGER.get(name, "interval")

    if is_global:
        actions = read_global_heartbeat(coral_dir, island_id=island_id)
        found = False
        for action in actions:
            if action["name"] == name:
                action["every"] = every
                action["trigger"] = trigger
                if prompt is not None:
                    action["prompt"] = prompt
                if epsilon is not None:
                    action.setdefault("options", {})["epsilon"] = epsilon
                found = True
                break
        if not found:
            new_action: dict = {
                "name": name,
                "every": every,
                "prompt": prompt if prompt is not None else DEFAULT_PROMPTS.get(name, ""),
                "trigger": trigger,
                "options": {"epsilon": epsilon} if epsilon is not None else {},
            }
            actions.append(new_action)
        write_global_heartbeat(coral_dir, actions, island_id=island_id)
        label = (
            f"after {every} non-improving eval(s) [plateau]"
            if trigger == "plateau"
            else f"every {every} eval(s)"
        )
        if trigger == "plateau" and epsilon is not None and epsilon > 0:
            label = f"{label} (epsilon={epsilon})"
        print(f"Set '{name}' to {label} (global) for all agents.")
    else:
        actions = read_agent_heartbeat(coral_dir, agent_id, island_id=island_id)
        found = False
        for action in actions:
            if action["name"] == name:
                action["every"] = every
                action["trigger"] = trigger
                if prompt is not None:
                    action["prompt"] = prompt
                if epsilon is not None:
                    action.setdefault("options", {})["epsilon"] = epsilon
                found = True
                break
        if not found:
            new_action = {
                "name": name,
                "every": every,
                "prompt": prompt if prompt is not None else DEFAULT_PROMPTS.get(name, ""),
                "trigger": trigger,
                "options": {"epsilon": epsilon} if epsilon is not None else {},
            }
            actions.append(new_action)
        write_agent_heartbeat(coral_dir, agent_id, actions, island_id=island_id)
        label = (
            f"after {every} non-improving eval(s) [plateau]"
            if trigger == "plateau"
            else f"every {every} eval(s)"
        )
        if trigger == "plateau" and epsilon is not None and epsilon > 0:
            label = f"{label} (epsilon={epsilon})"
        print(f"Set '{name}' to {label} (local) for {agent_id}.")


def _cmd_heartbeat_remove(args: argparse.Namespace) -> None:
    """Remove a heartbeat action."""
    from coral.hub.heartbeat import (
        PROTECTED_ACTIONS,
        read_agent_heartbeat,
        read_global_heartbeat,
        write_agent_heartbeat,
        write_global_heartbeat,
    )

    coral_dir, island_id = find_coral_dir_and_island(
        getattr(args, "task", None),
        getattr(args, "run", None),
    )
    _require_heartbeat_write_scope(coral_dir, island_id)
    agent_id = read_agent_id()
    name = args.name

    if name in PROTECTED_ACTIONS:
        print(
            f"Error: '{name}' is a protected action and cannot be removed.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Try removing from local first, then global
    local_actions = read_agent_heartbeat(coral_dir, agent_id, island_id=island_id)
    new_local = [a for a in local_actions if a["name"] != name]
    if len(new_local) < len(local_actions):
        write_agent_heartbeat(coral_dir, agent_id, new_local, island_id=island_id)
        print(f"Removed '{name}' (local) for {agent_id}.")
        return

    global_actions = read_global_heartbeat(coral_dir, island_id=island_id)
    new_global = [a for a in global_actions if a["name"] != name]
    if len(new_global) < len(global_actions):
        write_global_heartbeat(coral_dir, new_global, island_id=island_id)
        print(f"Removed '{name}' (global) for all agents.")
        return

    print(f"Action '{name}' not found for {agent_id}.", file=sys.stderr)
    sys.exit(1)


def _cmd_heartbeat_reset(args: argparse.Namespace) -> None:
    """Reset heartbeat config to defaults from task YAML."""
    from coral.config import CoralConfig
    from coral.hub.heartbeat import (
        default_global_actions,
        default_local_actions,
        write_agent_heartbeat,
        write_global_heartbeat,
    )

    coral_dir, island_id = find_coral_dir_and_island(
        getattr(args, "task", None),
        getattr(args, "run", None),
    )
    _require_heartbeat_write_scope(coral_dir, island_id)
    agent_id = read_agent_id()

    config_path = coral_dir / "config.yaml"
    if not config_path.exists():
        print("Error: No config.yaml found in .coral/.", file=sys.stderr)
        sys.exit(1)

    config = CoralConfig.from_yaml(config_path)
    write_agent_heartbeat(
        coral_dir,
        agent_id,
        default_local_actions(config),
        island_id=island_id,
    )
    write_global_heartbeat(
        coral_dir,
        default_global_actions(config),
        island_id=island_id,
    )
    print(f"Reset heartbeat config to defaults for {agent_id}.")
