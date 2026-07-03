"""Pluggable agent sandboxing (``agents.sandbox``)."""

from coral.sandbox.protocol import AgentSandboxContext, AgentSandboxSpec, SandboxProvider
from coral.sandbox.registry import get_sandbox_provider

__all__ = [
    "AgentSandboxContext",
    "AgentSandboxSpec",
    "SandboxProvider",
    "get_sandbox_provider",
]
