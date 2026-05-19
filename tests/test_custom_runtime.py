"""Custom runtime entrypoint loading via `agents.runtime: 'pkg.module:Cls'`."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from coral.agent import registry
from coral.agent.registry import (
    default_model_for_runtime,
    get_runtime,
)
from coral.agent.runtime import AgentHandle
from coral.config import CoralConfig

# ---------------------------------------------------------------------------
# Fixture: inject a fake runtime module into sys.modules so the registry can
# import it via `module.path:ClassName` without touching the filesystem.
# ---------------------------------------------------------------------------


class _FakeRuntime:
    """Minimal class satisfying the AgentRuntime structural protocol."""

    def start(
        self,
        worktree_path: Path,
        coral_md_path: Path,
        model: str = "any",
        runtime_options: dict[str, Any] | None = None,
        max_turns: int = 200,
        log_dir: Path | None = None,
        verbose: bool = False,
        resume_session_id: str | None = None,
        prompt: str | None = None,
        prompt_source: str | None = None,
        task_name: str | None = None,
        task_description: str | None = None,
        gateway_url: str | None = None,
        gateway_api_key: str | None = None,
    ) -> AgentHandle:  # pragma: no cover — never called in these tests
        raise NotImplementedError

    def extract_session_id(self, log_path: Path) -> str | None:  # pragma: no cover
        return None

    @property
    def instruction_filename(self) -> str:
        return "FAKE.md"

    @property
    def shared_dir_name(self) -> str:
        return ".fake"


class _NotARuntime:
    """Class that does NOT satisfy the AgentRuntime protocol."""

    def hello(self) -> str:  # pragma: no cover
        return "world"


@pytest.fixture
def fake_runtime_module() -> types.ModuleType:
    """Inject a fake module exposing _FakeRuntime + _NotARuntime."""
    mod_name = "coral_test_fake_runtime_module"
    module = types.ModuleType(mod_name)
    module.FakeRuntime = _FakeRuntime  # type: ignore[attr-defined]
    module.NotARuntime = _NotARuntime  # type: ignore[attr-defined]
    sys.modules[mod_name] = module
    yield module
    sys.modules.pop(mod_name, None)
    # Drop registry cache entries so other tests start clean.
    for key in list(registry._RUNTIMES):
        if ":" in key and key.startswith(mod_name + ":"):
            registry._RUNTIMES.pop(key, None)


# ---------------------------------------------------------------------------
# Successful resolution + caching
# ---------------------------------------------------------------------------


def test_get_runtime_loads_entrypoint(fake_runtime_module: types.ModuleType) -> None:
    spec = "coral_test_fake_runtime_module:FakeRuntime"
    instance = get_runtime(spec)
    assert isinstance(instance, _FakeRuntime)


def test_get_runtime_caches_entrypoint(fake_runtime_module: types.ModuleType) -> None:
    spec = "coral_test_fake_runtime_module:FakeRuntime"
    get_runtime(spec)
    assert spec in registry._RUNTIMES
    # Subsequent resolves should reuse the cached class without re-importing.
    sys.modules.pop("coral_test_fake_runtime_module")
    instance = get_runtime(spec)
    assert isinstance(instance, _FakeRuntime)


def test_default_model_for_runtime_returns_none_for_entrypoint() -> None:
    # Nothing registered, no module touched — pure name inspection.
    assert default_model_for_runtime("any.pkg:Anything") is None


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_get_runtime_errors_on_unknown_module() -> None:
    with pytest.raises(ImportError, match="Failed to import"):
        get_runtime("nonexistent_module_xyz:Whatever")


def test_get_runtime_errors_on_missing_attribute(
    fake_runtime_module: types.ModuleType,
) -> None:
    with pytest.raises(AttributeError, match="MissingClass"):
        get_runtime("coral_test_fake_runtime_module:MissingClass")


def test_get_runtime_errors_on_non_runtime_class(
    fake_runtime_module: types.ModuleType,
) -> None:
    with pytest.raises(TypeError, match="AgentRuntime protocol"):
        get_runtime("coral_test_fake_runtime_module:NotARuntime")


def test_get_runtime_errors_on_malformed_entrypoint() -> None:
    # Empty class name
    with pytest.raises(ValueError, match="module.path:ClassName"):
        get_runtime("some_module:")
    # Empty module name
    with pytest.raises(ValueError, match="module.path:ClassName"):
        get_runtime(":SomeClass")


def test_get_runtime_unknown_plain_name_still_errors() -> None:
    """Names without ':' fall through the original 'Unknown runtime' path."""
    with pytest.raises(ValueError, match="Unknown runtime"):
        get_runtime("not_a_real_runtime")


# ---------------------------------------------------------------------------
# Config-level guard: explicit agents.model required for entrypoint runtimes
# ---------------------------------------------------------------------------


def test_config_raises_when_entrypoint_runtime_without_model() -> None:
    with pytest.raises(ValueError, match="custom runtime entrypoint"):
        CoralConfig.from_dict(
            {
                "task": {"name": "t", "description": "d"},
                "agents": {"runtime": "coral_test_fake_runtime_module:FakeRuntime"},
            }
        )


def test_config_accepts_entrypoint_runtime_with_explicit_model() -> None:
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "agents": {
                "runtime": "coral_test_fake_runtime_module:FakeRuntime",
                "model": "my-custom-model",
            },
        }
    )
    assert cfg.agents.runtime == "coral_test_fake_runtime_module:FakeRuntime"
    assert cfg.agents.model == "my-custom-model"


def test_config_keeps_builtin_default_for_known_runtime() -> None:
    """Sanity check: existing default-model resolution path is unchanged."""
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "agents": {"runtime": "claude_code"},
        }
    )
    assert cfg.agents.model == "sonnet"
