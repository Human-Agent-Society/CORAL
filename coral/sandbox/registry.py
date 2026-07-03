"""Resolve ``agents.sandbox.provider`` names to provider instances.

Mirrors :mod:`coral.agent.registry`: built-in names map to bundled
implementations, and a ``module.path:ClassName`` entrypoint plugs in an
out-of-tree backend (e.g. an e2b or modal provider) without code changes
here. Imports are lazy so listing/validation never drags in backend deps.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coral.config import SandboxConfig
    from coral.sandbox.protocol import SandboxProvider

_BUILTIN: dict[str, str] = {
    "srt": "coral.sandbox.srt:SrtSandbox",
}


def get_sandbox_provider(cfg: SandboxConfig) -> SandboxProvider:
    """Instantiate the provider named by ``cfg.provider``."""
    name = cfg.provider
    entrypoint = _BUILTIN.get(name)
    if entrypoint is None and ":" in name:
        entrypoint = name
    if entrypoint is None:
        available = ", ".join(sorted(_BUILTIN))
        raise ValueError(
            f"Unknown sandbox provider {name!r}. Built-in providers: {available}. "
            f"For a custom backend, use a 'module.path:ClassName' entrypoint."
        )

    module_path, _, class_name = entrypoint.partition(":")
    try:
        cls = getattr(importlib.import_module(module_path), class_name)
    except (ImportError, AttributeError) as e:
        raise ValueError(f"Cannot load sandbox provider {entrypoint!r}: {e}") from e
    return cls(cfg)
