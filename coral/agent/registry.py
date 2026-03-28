"""Runtime registry — maps config strings to runtime implementations."""

from __future__ import annotations

from coral.agent.builtin.claude_code import ClaudeCodeRuntime
from coral.agent.builtin.codex import CodexRuntime
from coral.agent.builtin.kiro import KiroRuntime
from coral.agent.builtin.opencode import OpenCodeRuntime
from coral.agent.runtime import AgentRuntime

_RUNTIMES: dict[str, type] = {
    "claude_code": ClaudeCodeRuntime,
    "codex": CodexRuntime,
    "kiro": KiroRuntime,
    "opencode": OpenCodeRuntime,
}

# Convenience aliases
_ALIASES: dict[str, str] = {
    "claude": "claude_code",
    "claude-code": "claude_code",
    "openai": "codex",
    "openai-codex": "codex",
    "open-code": "opencode",
    "kiro-cli": "kiro",
}

# Default models per runtime (used when user doesn't specify --model)
_DEFAULT_MODELS: dict[str, str] = {
    "claude_code": "sonnet",
    "codex": "gpt-5.4",
    "kiro": "auto",
    "opencode": "openai/gpt-5",
}


def get_runtime(name: str) -> AgentRuntime:
    """Get a runtime instance by name.

    Supports canonical names (claude_code, codex, opencode) and aliases.
    """
    canonical = _ALIASES.get(name, name)
    cls = _RUNTIMES.get(canonical)
    if cls is None:
        available = sorted(set(list(_RUNTIMES.keys()) + list(_ALIASES.keys())))
        raise ValueError(
            f"Unknown runtime {name!r}. Available: {', '.join(available)}"
        )
    return cls()


def default_model_for_runtime(name: str) -> str | None:
    """Return the default model for a runtime, or None if unknown."""
    canonical = _ALIASES.get(name, name)
    return _DEFAULT_MODELS.get(canonical)


def register_runtime(name: str, cls: type, default_model: str | None = None) -> None:
    """Register a custom runtime class."""
    _RUNTIMES[name] = cls
    if default_model:
        _DEFAULT_MODELS[name] = default_model
