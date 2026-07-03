"""Sandbox provider protocol — pluggable isolation backends for agents.

A sandbox provider is the containment counterpart of an agent runtime: the
runtime decides *what* command runs an agent, the provider decides *how
contained* that command is. Providers are resolved by name from
``agents.sandbox.provider`` (see :mod:`coral.sandbox.registry`) — ``srt``
is the built-in default; hosted backends (e2b, modal, ...) plug in as
custom entrypoints without touching runtimes or the manager.

The contract is deliberately narrow: :meth:`SandboxProvider.prepare_agent`
returns an :class:`AgentSandboxSpec` whose ``command_prefix`` wraps the
runtime command and whose ``env`` is merged into the agent's environment.
The wrapped command MUST still behave like a local process — stream stdio,
propagate exit codes and signals, and see the worktree path — because the
manager supervises it through the same ``AgentHandle`` machinery as an
unsandboxed agent. A local enforcer (srt, bwrap, docker run) satisfies
this directly; a remote backend satisfies it with a shim command that
syncs the worktree and tunnels execution.

Lifecycle: ``validate`` (fail fast on missing deps / config conflicts,
before any run state is created) → ``start`` (run-level resources: a
network proxy, a VM pool, an API session) → ``prepare_agent`` per agent
(re-invoked on every restart/resume, so specs may embed live state like a
proxy port) → ``stop`` (teardown with the run).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from coral.config import AgentConfig


@dataclass
class AgentSandboxContext:
    """Everything a provider may need to build one agent's containment."""

    agent_id: str
    worktree_path: Path
    coral_dir: Path
    repo_dir: Path
    # The runtime's native shared-state dir name (".claude", ".codex", ...) —
    # providers use it to grant the runtime CLI's own home state.
    shared_dir_name: str
    # Worktrees of this agent's collaborators (island-mates in multi-island
    # runs), own worktree included. Supplied from the manager's roster, which
    # is authoritative even when the paths don't exist on disk yet (initial
    # start spawns agents one by one) or a breadcrumb is mid-rewrite
    # (migration). Empty means "provider decides" (e.g. srt falls back to
    # on-disk breadcrumbs).
    sibling_worktrees: list[Path] = field(default_factory=list)


@dataclass
class AgentSandboxSpec:
    """How to launch one agent inside the sandbox.

    ``command_prefix`` is prepended to the runtime command (see
    :func:`coral.agent.runtime.apply_sandbox`); ``env`` is merged into the
    agent subprocess environment (secrets belong here, not in the prefix —
    argv is visible in ``ps``).
    """

    command_prefix: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class SandboxProvider(Protocol):
    """Protocol all sandbox backends implement.

    Constructed with the run's ``SandboxConfig`` (see the registry); must be
    safe to construct even when the backend's dependencies are absent —
    dependency checks belong in ``validate``.
    """

    def validate(self, agents: AgentConfig) -> None:
        """Raise RuntimeError (with an actionable message) if this backend
        cannot work here — missing binaries, conflicting agent config."""
        ...

    def start(self) -> None:
        """Bring up run-level resources. Idempotent."""
        ...

    def stop(self) -> None:
        """Tear down whatever ``start`` created. Safe to call when idle."""
        ...

    def prepare_agent(self, ctx: AgentSandboxContext) -> AgentSandboxSpec:
        """Build the launch spec for one agent. Called on every (re)start."""
        ...
