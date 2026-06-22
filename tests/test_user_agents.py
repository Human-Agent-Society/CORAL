"""Tests for user-level agent bindings: storage, config expansion, and CLI."""

from __future__ import annotations

import argparse

import pytest
import yaml

from coral.agent.assignments import resolve_agent_specs
from coral.config import CoralConfig
from coral.user_agents import AgentBinding, BindingStore, load_store, save_store, user_config_path


@pytest.fixture
def bindings_file(tmp_path, monkeypatch):
    """Point the user-level bindings file at a temp path for the test."""
    path = tmp_path / "agents.yaml"
    monkeypatch.setenv("CORAL_AGENTS_CONFIG", str(path))
    return path


def _write(path, data):
    with open(path, "w") as f:
        yaml.dump(data, f)


# --- storage ------------------------------------------------------------------


def test_user_config_path_honors_env(monkeypatch, tmp_path):
    target = tmp_path / "custom.yaml"
    monkeypatch.setenv("CORAL_AGENTS_CONFIG", str(target))
    assert user_config_path() == target


def test_user_config_path_honors_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("CORAL_AGENTS_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert user_config_path() == tmp_path / "coral" / "agents.yaml"


def test_load_missing_file_returns_empty(bindings_file):
    store = load_store()
    assert store.bindings == {}
    assert store.default is None


def test_save_and_load_roundtrip(bindings_file):
    store = BindingStore(
        bindings={
            "claude-opus": AgentBinding(
                name="claude-opus",
                runtime="claude_code",
                command="claude",
                model="opus",
                role_file="~/roles/generalist.md",
            ),
            "codex-high": AgentBinding(
                name="codex-high",
                runtime="codex",
                command="codex",
                model="gpt-5.4",
                runtime_options={"model_reasoning_effort": "high"},
            ),
        },
        default="claude-opus",
    )
    save_store(store, bindings_file)

    restored = load_store()
    assert set(restored.bindings) == {"claude-opus", "codex-high"}
    assert restored.default == "claude-opus"
    assert restored.bindings["codex-high"].runtime_options == {"model_reasoning_effort": "high"}
    assert restored.bindings["claude-opus"].role_file == "~/roles/generalist.md"


def test_load_rejects_missing_runtime(bindings_file):
    _write(bindings_file, {"agents": {"bad": {"model": "opus"}}})
    with pytest.raises(ValueError, match="missing required field 'runtime'"):
        load_store()


def test_load_rejects_unknown_default(bindings_file):
    _write(bindings_file, {"default": "ghost", "agents": {"x": {"runtime": "claude_code"}}})
    with pytest.raises(ValueError, match="default binding"):
        load_store()


# --- config expansion ---------------------------------------------------------


def _seed(bindings_file):
    _write(
        bindings_file,
        {
            "default": "claude-opus",
            "agents": {
                "claude-opus": {
                    "runtime": "claude_code",
                    "command": "claude",
                    "model": "opus",
                    "role_file": "/tmp/generalist.md",
                },
                "codex-high": {
                    "runtime": "codex",
                    "command": "codex",
                    "model": "gpt-5.4",
                    "runtime_options": {"model_reasoning_effort": "high"},
                },
            },
        },
    )


def test_top_level_binding_expands(bindings_file):
    _seed(bindings_file)
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "agents": {"binding": "claude-opus", "count": 3},
        }
    )
    assert cfg.agents.runtime == "claude_code"
    assert cfg.agents.model == "opus"
    assert cfg.agents.count == 3
    assert cfg.agents.runtime_options["role_file"] == "/tmp/generalist.md"
    specs = resolve_agent_specs(cfg)
    assert len(specs) == 3
    assert all(s.runtime == "claude_code" and s.model == "opus" for s in specs)


def test_explicit_field_overrides_binding(bindings_file):
    _seed(bindings_file)
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "agents": {"binding": "claude-opus", "model": "sonnet"},
        }
    )
    # binding runtime is kept, but the explicit model wins
    assert cfg.agents.runtime == "claude_code"
    assert cfg.agents.model == "sonnet"


def test_assignment_binding_expands(bindings_file):
    _seed(bindings_file)
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "agents": {
                "assignments": [
                    {"binding": "claude-opus", "count": 1},
                    {"binding": "codex-high", "count": 2},
                ]
            },
        }
    )
    specs = resolve_agent_specs(cfg)
    assert len(specs) == 3
    assert specs[0].runtime == "claude_code"
    assert specs[0].model == "opus"
    assert specs[1].runtime == "codex"
    assert specs[1].model == "gpt-5.4"
    assert specs[1].runtime_options["model_reasoning_effort"] == "high"


def test_assignment_binding_field_override(bindings_file):
    _seed(bindings_file)
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "agents": {
                "assignments": [
                    {"binding": "codex-high", "model": "gpt-5.4-mini", "count": 1},
                ]
            },
        }
    )
    specs = resolve_agent_specs(cfg)
    assert specs[0].runtime == "codex"
    assert specs[0].model == "gpt-5.4-mini"


def test_unknown_binding_raises(bindings_file):
    _seed(bindings_file)
    with pytest.raises(ValueError, match="is not defined"):
        CoralConfig.from_dict(
            {
                "task": {"name": "t", "description": "d"},
                "agents": {"binding": "ghost"},
            }
        )


def test_binding_removed_from_serialized_config(bindings_file):
    _seed(bindings_file)
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "agents": {"binding": "claude-opus"},
        }
    )
    # binding is a load-time shorthand; it must not survive into the schema.
    assert "binding" not in cfg.to_dict()["agents"]


def test_custom_command_forwarded_when_divergent(bindings_file):
    # cursor_agent honors runtime_options.command; a non-default command path
    # should be compiled into runtime_options.
    _write(
        bindings_file,
        {
            "agents": {
                "my-cursor": {
                    "runtime": "cursor_agent",
                    "command": "/opt/cursor/cursor-agent",
                    "model": "auto",
                }
            }
        },
    )
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "agents": {"binding": "my-cursor"},
        }
    )
    assert cfg.agents.runtime_options["command"] == "/opt/cursor/cursor-agent"


def test_default_command_not_forwarded(bindings_file):
    # The common case (command == runtime default) stays out of runtime_options.
    _seed(bindings_file)
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "agents": {"binding": "claude-opus"},
        }
    )
    assert "command" not in cfg.agents.runtime_options


def test_cli_doctor_reports_missing_cli(bindings_file, capsys):
    from coral.cli.agents import cmd_agents, cmd_setup

    cmd_setup(
        _ns(
            setup_command="agent",
            name="ghost-cli",
            runtime="claude_code",
            command_path="/nonexistent/definitely-not-a-real-binary",
            model="opus",
            role_file=None,
            option=[],
            default=False,
            non_interactive=True,
            config=None,
        )
    )
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        cmd_agents(_ns(agents_command="doctor", name="ghost-cli", config=None))
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "PROBLEMS" in out
    assert "CLI found" in out


def test_config_without_bindings_does_not_touch_file(monkeypatch, tmp_path):
    # Even if a (broken) file exists, configs that don't reference a binding
    # must load fine — the file is only read when a binding is referenced.
    bad = tmp_path / "agents.yaml"
    bad.write_text("this: [is, not, valid: structure")
    monkeypatch.setenv("CORAL_AGENTS_CONFIG", str(bad))
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "agents": {"runtime": "claude_code", "model": "sonnet"},
        }
    )
    assert cfg.agents.runtime == "claude_code"


# --- CLI ----------------------------------------------------------------------


def _ns(**kw):
    return argparse.Namespace(**kw)


def test_cli_setup_agent_creates_binding(bindings_file, capsys):
    from coral.cli.agents import cmd_setup

    cmd_setup(
        _ns(
            setup_command="agent",
            name="my-claude",
            runtime="claude_code",
            command_path=None,
            model="opus",
            role_file=None,
            option=[],
            default=False,
            non_interactive=True,
            config=None,
        )
    )
    store = load_store()
    assert "my-claude" in store.bindings
    assert store.bindings["my-claude"].model == "opus"
    # first binding becomes default
    assert store.default == "my-claude"


def test_cli_setup_rejects_unknown_runtime(bindings_file):
    from coral.cli.agents import cmd_setup

    with pytest.raises(SystemExit):
        cmd_setup(
            _ns(
                setup_command="agent",
                name="x",
                runtime="not_a_runtime",
                command_path=None,
                model="m",
                role_file=None,
                option=[],
                default=False,
                non_interactive=True,
                config=None,
            )
        )


def test_cli_setup_parses_options(bindings_file):
    from coral.cli.agents import cmd_setup

    cmd_setup(
        _ns(
            setup_command="agent",
            name="codex-high",
            runtime="codex",
            command_path=None,
            model="gpt-5.4",
            role_file=None,
            option=["model_reasoning_effort=high", "foo=3", "flag=true"],
            default=False,
            non_interactive=True,
            config=None,
        )
    )
    b = load_store().bindings["codex-high"]
    assert b.runtime_options == {
        "model_reasoning_effort": "high",
        "foo": 3,
        "flag": True,
    }


def test_cli_agents_list_and_remove(bindings_file, capsys):
    from coral.cli.agents import cmd_agents, cmd_setup

    cmd_setup(
        _ns(
            setup_command="agent",
            name="a1",
            runtime="claude_code",
            command_path=None,
            model="opus",
            role_file=None,
            option=[],
            default=False,
            non_interactive=True,
            config=None,
        )
    )
    capsys.readouterr()
    cmd_agents(_ns(agents_command="list", config=None))
    out = capsys.readouterr().out
    assert "a1" in out
    assert "default" in out

    cmd_agents(_ns(agents_command="remove", name="a1", config=None))
    assert "a1" not in load_store().bindings
