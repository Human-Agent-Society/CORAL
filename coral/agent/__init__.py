"""Agent lifecycle management."""

from coral.agent.builtin.claude_code import ClaudeCodeRuntime
from coral.agent.builtin.codex import CodexRuntime
from coral.agent.builtin.opencode import OpenCodeRuntime
from coral.agent.manager import AgentManager
from coral.agent.registry import get_runtime, register_runtime
from coral.agent.runtime import AgentRuntime

__all__ = [
    "AgentManager",
    "AgentRuntime",
    "ClaudeCodeRuntime",
    "CodexRuntime",
    "OpenCodeRuntime",
    "get_runtime",
    "register_runtime",
]
