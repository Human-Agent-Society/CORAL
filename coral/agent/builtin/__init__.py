"""Built-in agent runtime implementations."""

from coral.agent.builtin.claude_code import ClaudeCodeRuntime
from coral.agent.builtin.codex import CodexRuntime
from coral.agent.builtin.cursor_agent import CursorAgentRuntime
from coral.agent.builtin.opencode import OpenCodeRuntime

__all__ = [
    "ClaudeCodeRuntime",
    "CodexRuntime",
    "CursorAgentRuntime",
    "OpenCodeRuntime",
]
