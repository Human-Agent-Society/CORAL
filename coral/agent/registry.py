"""Runtime registry — maps config strings to runtime implementations."""

from __future__ import annotations

import importlib

from coral.agent.builtin.claude_code import ClaudeCodeRuntime
from coral.agent.builtin.codex import CodexRuntime
from coral.agent.builtin.cursor_agent import CursorAgentRuntime
from coral.agent.builtin.kiro import KiroRuntime
from coral.agent.builtin.opencode import OpenCodeRuntime
from coral.agent.builtin.pi_agent import PiAgentRuntime
from coral.agent.runtime import AgentRuntime

_RUNTIMES: dict[str, type] = {
    "claude_code": ClaudeCodeRuntime,
    "codex": CodexRuntime,
    "cursor_agent": CursorAgentRuntime,
    "kiro": KiroRuntime,
    "opencode": OpenCodeRuntime,
    "pi": PiAgentRuntime,
}

# Convenience aliases
_ALIASES: dict[str, str] = {
    "claude": "claude_code",
    "claude-code": "claude_code",
    "openai": "codex",
    "openai-codex": "codex",
    "open-code": "opencode",
    "kiro-cli": "kiro",
    "cursor": "cursor_agent",
    "cursor-agent": "cursor_agent",
    "pi-agent": "pi",
}

# Default models per runtime (used when user doesn't specify --model)
_DEFAULT_MODELS: dict[str, str] = {
    "claude_code": "sonnet",
    "codex": "gpt-5.4",
    "cursor_agent": "auto",
    "kiro": "auto",
    "opencode": "openai/gpt-5",
    "pi": "zai/glm-5.1",
}


def _is_entrypoint(name: str) -> bool:
    return ":" in name


def _load_entrypoint(spec: str) -> type:
    """Resolve 'module.path:ClassName' and verify it satisfies AgentRuntime."""
    if spec.count(":") != 1:
        raise ValueError(f"Custom runtime entrypoint must be 'module.path:ClassName', got {spec!r}")
    mod_path, cls_name = spec.split(":", 1)
    if not mod_path or not cls_name:
        raise ValueError(f"Custom runtime entrypoint must be 'module.path:ClassName', got {spec!r}")
    try:
        module = importlib.import_module(mod_path)
    except ImportError as e:
        raise ImportError(
            f"Failed to import custom runtime module {mod_path!r}: {e}. "
            f"Install the package in the same environment as `coral` (e.g. `uv pip install -e .`)."
        ) from e
    try:
        cls = getattr(module, cls_name)
    except AttributeError as e:
        raise AttributeError(f"Module {mod_path!r} has no attribute {cls_name!r}") from e
    try:
        instance = cls()
    except Exception as e:
        raise TypeError(
            f"Custom runtime {spec} could not be instantiated with no arguments: {e}"
        ) from e
    if not isinstance(instance, AgentRuntime):
        raise TypeError(
            f"Custom runtime {spec} does not satisfy the AgentRuntime protocol "
            f"(see coral/agent/runtime.py for the required methods)."
        )
    return cls


def get_runtime(name: str) -> AgentRuntime:
    """Get a runtime instance by name.

    Supports canonical names (claude_code, codex, opencode), aliases, and
    custom entrypoints of the form 'module.path:ClassName' — the entrypoint
    is imported on first use and cached in `_RUNTIMES`.
    """
    canonical = _ALIASES.get(name, name)
    cls = _RUNTIMES.get(canonical)
    if cls is None and _is_entrypoint(canonical):
        cls = _load_entrypoint(canonical)
        _RUNTIMES[canonical] = cls
    if cls is None:
        available = sorted(set(list(_RUNTIMES.keys()) + list(_ALIASES.keys())))
        raise ValueError(
            f"Unknown runtime {name!r}. Available: {', '.join(available)}. "
            f"For a custom runtime, set agents.runtime = 'module.path:ClassName'."
        )
    return cls()


def default_model_for_runtime(name: str) -> str | None:
    """Return the default model for a runtime, or None if unknown.

    Returns None for custom entrypoint runtimes — users must set
    `agents.model` explicitly when wiring their own runtime.
    """
    canonical = _ALIASES.get(name, name)
    if _is_entrypoint(canonical):
        return None
    return _DEFAULT_MODELS.get(canonical)


def register_runtime(name: str, cls: type, default_model: str | None = None) -> None:
    """Register a custom runtime class."""
    _RUNTIMES[name] = cls
    if default_model:
        _DEFAULT_MODELS[name] = default_model
