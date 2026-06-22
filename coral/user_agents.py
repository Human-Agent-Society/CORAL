"""User-level agent bindings.

A *binding* is a named, machine-local preset that bundles an agent runtime,
its CLI command, a default model, runtime options, and an optional role seed
file. Tasks reference a binding by name (``agents.binding`` or
``agents.assignments[].binding``) instead of repeating those details in every
``task.yaml``.

Bindings live in a single user-level YAML file, by default
``~/.config/coral/agents.yaml`` (override with ``$CORAL_AGENTS_CONFIG`` or
``$XDG_CONFIG_HOME``). This is *not* a replacement for the per-run
``agents.runtime`` / ``agents.model`` / ``agents.assignments`` machinery —
bindings expand into those concrete fields at config-load time (see
``coral.config._expand_bindings``). The manager only ever consumes resolved
``AgentSpec`` objects.

No secrets are ever stored here: bindings hold runtime/model/command metadata
only, never API keys, OAuth tokens, or provider credentials. Runtime-native
login flows (``claude``, ``codex``, ``cursor-agent login``, ...) own auth.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AgentBinding:
    """A named user-level agent preset.

    ``command`` is the CLI binary used for validation (``coral agents doctor``)
    and, where a runtime supports it (e.g. ``cursor_agent``), forwarded as a
    runtime option. ``role_file`` is compiled into ``runtime_options.role_file``
    at expansion time.
    """

    name: str
    runtime: str
    command: str = ""
    model: str = ""
    runtime_options: dict[str, Any] = field(default_factory=dict)
    role_file: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"runtime": self.runtime}
        if self.command:
            out["command"] = self.command
        if self.model:
            out["model"] = self.model
        if self.runtime_options:
            out["runtime_options"] = dict(self.runtime_options)
        if self.role_file:
            out["role_file"] = self.role_file
        return out

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> AgentBinding:
        if not isinstance(data, dict):
            raise ValueError(f"binding {name!r} must be a mapping, got {type(data).__name__}")
        runtime = data.get("runtime", "")
        if not runtime:
            raise ValueError(f"binding {name!r} is missing required field 'runtime'")
        opts = data.get("runtime_options") or {}
        if not isinstance(opts, dict):
            raise ValueError(f"binding {name!r}: runtime_options must be a mapping")
        return cls(
            name=name,
            runtime=str(runtime),
            command=str(data.get("command", "") or ""),
            model=str(data.get("model", "") or ""),
            runtime_options=dict(opts),
            role_file=str(data.get("role_file", "") or ""),
        )


@dataclass
class BindingStore:
    """The full contents of the user-level bindings file."""

    bindings: dict[str, AgentBinding] = field(default_factory=dict)
    default: str | None = None
    path: Path | None = None

    def get(self, name: str) -> AgentBinding | None:
        return self.bindings.get(name)

    def resolve_default(self) -> AgentBinding | None:
        if self.default and self.default in self.bindings:
            return self.bindings[self.default]
        return None


def user_config_path() -> Path:
    """Return the path to the user-level agents.yaml.

    Honors ``$CORAL_AGENTS_CONFIG`` (full path override, used in tests) and
    ``$XDG_CONFIG_HOME``, falling back to ``~/.config/coral/agents.yaml``.
    """
    override = os.environ.get("CORAL_AGENTS_CONFIG")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "coral" / "agents.yaml"


def load_store(path: Path | None = None) -> BindingStore:
    """Load the bindings file. Returns an empty store if it does not exist."""
    path = path or user_config_path()
    if not path.exists():
        return BindingStore(path=path)
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level content must be a mapping")
    raw_bindings = data.get("agents") or {}
    if not isinstance(raw_bindings, dict):
        raise ValueError(f"{path}: 'agents' must be a mapping of name -> binding")
    bindings = {name: AgentBinding.from_dict(name, entry) for name, entry in raw_bindings.items()}
    default = data.get("default")
    if default is not None and default not in bindings:
        raise ValueError(f"{path}: default binding {default!r} is not defined under 'agents'")
    return BindingStore(bindings=bindings, default=default, path=path)


def save_store(store: BindingStore, path: Path | None = None) -> Path:
    """Write the bindings file (creating parent dirs). Returns the path written."""
    path = path or store.path or user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    out: dict[str, Any] = {}
    if store.default:
        out["default"] = store.default
    out["agents"] = {name: b.to_dict() for name, b in store.bindings.items()}
    with open(path, "w") as f:
        yaml.dump(out, f, default_flow_style=False, sort_keys=True)
    return path


def get_binding(name: str, path: Path | None = None) -> AgentBinding | None:
    """Convenience: load the store and return a single binding by name."""
    return load_store(path).get(name)
