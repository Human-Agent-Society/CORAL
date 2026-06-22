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


def _seed_real_path_binding(name: str, runtime: str = "claude_code"):
    """Create a binding pointing at /bin/sh (always exists) so doctor can
    actually exercise the CLI-found + --version + ping code paths.
    """
    from coral.cli.agents import cmd_setup

    cmd_setup(
        _ns(
            setup_command="agent",
            name=name,
            runtime=runtime,
            command_path="/bin/sh",
            model="opus",
            role_file=None,
            option=[],
            default=False,
            non_interactive=True,
            config=None,
        )
    )


def _make_fake_run(
    ping_stdout: str = "ok\n",
    ping_rc: int = 0,
    ping_stderr: str = "",
    *,
    raise_timeout: bool = False,
):
    """Build a subprocess.run fake that special-cases --version vs. ping."""
    import subprocess as _sp

    def fake_run(argv, **kwargs):
        args_after = argv[1:]
        if args_after and args_after[0] in ("--version", "version"):
            return _sp.CompletedProcess(argv, 0, stdout="fake-version 1.0\n", stderr="")
        if raise_timeout:
            raise _sp.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout", 0))
        return _sp.CompletedProcess(argv, ping_rc, stdout=ping_stdout, stderr=ping_stderr)

    return fake_run


def test_doctor_live_ping_success(bindings_file, monkeypatch, capsys):
    from coral.cli.agents import cmd_agents

    _seed_real_path_binding("good")
    monkeypatch.setattr("coral.cli.agents.subprocess.run", _make_fake_run())
    capsys.readouterr()

    with pytest.raises(SystemExit) as exc:
        cmd_agents(
            _ns(
                agents_command="doctor",
                name="good",
                config=None,
                no_live=False,
                timeout=5.0,
            )
        )
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "live ping" in out
    assert "reply received" in out
    assert "OK" in out


def test_doctor_no_live_skips_ping(bindings_file, monkeypatch, capsys):
    from coral.cli.agents import cmd_agents

    _seed_real_path_binding("good")
    # Even if subprocess.run would fail, --no-live should never call it for ping.
    monkeypatch.setattr(
        "coral.cli.agents.subprocess.run",
        _make_fake_run(ping_stdout="", ping_rc=99),
    )
    capsys.readouterr()

    with pytest.raises(SystemExit) as exc:
        cmd_agents(
            _ns(
                agents_command="doctor",
                name="good",
                config=None,
                no_live=True,
                timeout=5.0,
            )
        )
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "live ping" not in out
    assert "OK" in out


def test_doctor_live_ping_timeout(bindings_file, monkeypatch, capsys):
    from coral.cli.agents import cmd_agents

    _seed_real_path_binding("slow")
    monkeypatch.setattr(
        "coral.cli.agents.subprocess.run",
        _make_fake_run(raise_timeout=True),
    )
    capsys.readouterr()

    with pytest.raises(SystemExit) as exc:
        cmd_agents(
            _ns(
                agents_command="doctor",
                name="slow",
                config=None,
                no_live=False,
                timeout=2.0,
            )
        )
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "timed out after 2s" in out


def test_doctor_live_ping_nonzero_exit(bindings_file, monkeypatch, capsys):
    from coral.cli.agents import cmd_agents

    _seed_real_path_binding("broken")
    monkeypatch.setattr(
        "coral.cli.agents.subprocess.run",
        _make_fake_run(ping_stdout="", ping_rc=2, ping_stderr="auth failed: not logged in"),
    )
    capsys.readouterr()

    with pytest.raises(SystemExit) as exc:
        cmd_agents(
            _ns(
                agents_command="doctor",
                name="broken",
                config=None,
                no_live=False,
                timeout=5.0,
            )
        )
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "exit 2" in out
    assert "auth failed" in out


def test_doctor_live_ping_unsupported_runtime(bindings_file, monkeypatch, capsys):
    """kiro has no documented non-interactive mode → ping reports
    'not implemented' rather than spawning the CLI."""
    from coral.cli.agents import cmd_agents

    _seed_real_path_binding("ki", runtime="kiro")
    # Any subprocess.run beyond --version would be wrong — verify it's NOT called
    # for ping. We do this by making the fake intentionally fail any non-version
    # call and asserting the doctor row says 'not implemented' instead.
    sentinel_called = {"ping": False}

    import subprocess as _sp

    def fake_run(argv, **kwargs):
        if argv[1:] and argv[1] in ("--version", "version"):
            return _sp.CompletedProcess(argv, 0, stdout="ok\n", stderr="")
        sentinel_called["ping"] = True
        return _sp.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr("coral.cli.agents.subprocess.run", fake_run)
    capsys.readouterr()

    with pytest.raises(SystemExit):
        cmd_agents(
            _ns(
                agents_command="doctor",
                name="ki",
                config=None,
                no_live=False,
                timeout=5.0,
            )
        )
    assert sentinel_called["ping"] is False, "should not have spawned kiro for ping"
    assert "not implemented" in capsys.readouterr().out


def test_setup_agent_auto_doctor_does_not_ping(bindings_file, monkeypatch, capsys):
    """The auto-doctor pass at the end of `coral setup agent` is metadata-only
    by design — it must NOT trigger an LLM round-trip."""
    from coral.cli.agents import cmd_setup

    called = {"ping": False}
    import subprocess as _sp

    def fake_run(argv, **kwargs):
        if argv[1:] and argv[1] in ("--version", "version"):
            return _sp.CompletedProcess(argv, 0, stdout="fake-version 1.0\n", stderr="")
        called["ping"] = True
        return _sp.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr("coral.cli.agents.subprocess.run", fake_run)

    cmd_setup(
        _ns(
            setup_command="agent",
            name="quick",
            runtime="claude_code",
            command_path="/bin/sh",
            model="opus",
            role_file=None,
            option=[],
            default=False,
            non_interactive=True,
            config=None,
        )
    )
    assert called["ping"] is False
    assert "live ping" not in capsys.readouterr().out


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

    cmd_agents(_ns(agents_command="remove", names=["a1"], config=None))
    assert "a1" not in load_store().bindings


def _seed_two_bindings(store_path):
    """Helper: drop two pre-made bindings into the store."""
    from coral.cli.agents import cmd_setup

    for name, runtime, model in [("a1", "claude_code", "opus"), ("a2", "codex", "gpt-5.4")]:
        cmd_setup(
            _ns(
                setup_command="agent",
                name=name,
                runtime=runtime,
                command_path=None,
                model=model,
                role_file=None,
                option=[],
                default=False,
                non_interactive=True,
                config=None,
            )
        )


def test_cli_agents_list_shows_indices(bindings_file, capsys):
    from coral.cli.agents import cmd_agents

    _seed_two_bindings(bindings_file)
    capsys.readouterr()
    cmd_agents(_ns(agents_command="list", config=None))
    out = capsys.readouterr().out
    assert "[1] a1" in out
    assert "[2] a2" in out
    # Help footer points at the interactive remove.
    assert "coral agents remove" in out


def test_cli_agents_remove_variadic_removes_many(bindings_file, capsys):
    from coral.cli.agents import cmd_agents

    _seed_two_bindings(bindings_file)
    capsys.readouterr()
    cmd_agents(_ns(agents_command="remove", names=["a1", "a2"], config=None))
    assert load_store().bindings == {}


def test_cli_agents_remove_rejects_unknown_name_without_changes(bindings_file, capsys):
    from coral.cli.agents import cmd_agents

    _seed_two_bindings(bindings_file)
    capsys.readouterr()
    with pytest.raises(SystemExit):
        cmd_agents(_ns(agents_command="remove", names=["a1", "ghost"], config=None))
    # Pre-validation aborts BEFORE any removal — both bindings still exist.
    assert set(load_store().bindings) == {"a1", "a2"}


def test_cli_agents_remove_interactive_picker(bindings_file, monkeypatch, capsys):
    from coral.cli.agents import cmd_agents

    _seed_two_bindings(bindings_file)
    capsys.readouterr()

    # Pick #1 (a1), confirm with 'y'.
    answers = iter(["1", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    cmd_agents(_ns(agents_command="remove", names=[], config=None))

    assert set(load_store().bindings) == {"a2"}
    out = capsys.readouterr().out
    # `input()`'s prompt text isn't captured (the mock discards it); just
    # verify the success line emitted by the command itself.
    assert "✓ removed 'a1'" in out


def test_cli_agents_remove_interactive_confirm_no_aborts(bindings_file, monkeypatch, capsys):
    from coral.cli.agents import cmd_agents

    _seed_two_bindings(bindings_file)
    capsys.readouterr()

    answers = iter(["1,2", "n"])  # pick all, then say no
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    cmd_agents(_ns(agents_command="remove", names=[], config=None))
    # No deletion happened.
    assert set(load_store().bindings) == {"a1", "a2"}
    assert "No bindings removed" in capsys.readouterr().out


def test_cli_agents_remove_interactive_empty_selection(bindings_file, monkeypatch, capsys):
    from coral.cli.agents import cmd_agents

    _seed_two_bindings(bindings_file)
    capsys.readouterr()

    # Hit Enter immediately to cancel.
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    cmd_agents(_ns(agents_command="remove", names=[], config=None))
    assert set(load_store().bindings) == {"a1", "a2"}
    assert "No bindings removed" in capsys.readouterr().out


def test_cli_agents_remove_reassigns_default(bindings_file, monkeypatch, capsys):
    from coral.cli.agents import cmd_agents

    _seed_two_bindings(bindings_file)
    # a1 was first → it's the default.
    assert load_store().default == "a1"
    capsys.readouterr()

    cmd_agents(_ns(agents_command="remove", names=["a1"], config=None))
    store = load_store()
    assert "a1" not in store.bindings
    assert store.default == "a2"
    assert "New default: a2" in capsys.readouterr().out


def test_cli_agents_remove_with_empty_store(bindings_file, capsys):
    from coral.cli.agents import cmd_agents

    cmd_agents(_ns(agents_command="remove", names=[], config=None))
    out = capsys.readouterr().out
    assert "No agent bindings defined" in out


# --- runtime auto-detection ---------------------------------------------------


def test_detect_available_runtimes_includes_all_canonical(monkeypatch):
    """Detection returns one row per canonical runtime, found or not."""
    from coral.agent.registry import detect_available_runtimes, known_runtimes

    # Force shutil.which to always succeed so we can verify the schema.
    monkeypatch.setattr("coral.agent.registry.shutil.which", lambda cmd: f"/fake/bin/{cmd}")
    rows = detect_available_runtimes()
    assert [r["runtime"] for r in rows] == known_runtimes()
    for r in rows:
        assert set(r.keys()) == {"runtime", "command", "resolved", "model"}
        assert r["resolved"] == f"/fake/bin/{r['command']}"


def test_detect_marks_missing_runtimes(monkeypatch):
    """When a CLI is not on PATH, resolved is None."""
    from coral.agent.registry import detect_available_runtimes

    monkeypatch.setattr("coral.agent.registry.shutil.which", lambda cmd: None)
    rows = detect_available_runtimes()
    assert rows  # has rows
    assert all(r["resolved"] is None for r in rows)


def test_setup_detect_reports_when_no_cli_found(bindings_file, monkeypatch, capsys):
    """`coral setup` with nothing on PATH prints guidance and exits cleanly."""
    from coral.cli.agents import cmd_setup

    monkeypatch.setattr("coral.agent.registry.shutil.which", lambda cmd: None)
    cmd_setup(_ns(setup_command=None, non_interactive=True, config=None))
    out = capsys.readouterr().out
    assert "Scanning PATH" in out
    assert "not found" in out
    assert "No agent CLIs found on PATH" in out


def test_setup_detect_non_interactive_lists_detected(bindings_file, monkeypatch, capsys):
    """Non-interactive `coral setup` just prints the detection report."""
    from coral.cli.agents import cmd_setup

    # Pretend `claude` is on PATH but nothing else is.
    def fake_which(cmd):
        return "/usr/local/bin/claude" if cmd == "claude" else None

    monkeypatch.setattr("coral.agent.registry.shutil.which", fake_which)
    cmd_setup(_ns(setup_command=None, non_interactive=True, config=None))
    out = capsys.readouterr().out
    assert "claude_code" in out
    assert "/usr/local/bin/claude" in out
    # Other runtimes still listed, but marked not found.
    assert "not found" in out
    # No binding was actually created.
    assert load_store().bindings == {}


def test_setup_detect_interactive_creates_binding(bindings_file, monkeypatch, capsys):
    """In a TTY, the wizard creates bindings for selected detected runtimes."""
    from coral.cli.agents import cmd_setup

    def fake_which(cmd):
        return "/usr/local/bin/claude" if cmd == "claude" else None

    monkeypatch.setattr("coral.agent.registry.shutil.which", fake_which)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    # Pick runtime #1, accept default name, accept default model, skip role_file, 'n' to "add another?"
    answers = iter(["1", "", "", "", "n"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    cmd_setup(_ns(setup_command=None, non_interactive=False, config=None))

    store = load_store()
    # Default name comes from runtime "claude_code" -> "claude-code"
    assert "claude-code" in store.bindings
    binding = store.bindings["claude-code"]
    assert binding.runtime == "claude_code"
    assert binding.command == "claude"
    assert binding.model == "sonnet"  # registry default
    # First-created binding becomes default.
    assert store.default == "claude-code"
    out = capsys.readouterr().out
    assert "Saved 1 binding(s)" in out


def test_setup_detect_multiple_bindings_per_runtime(bindings_file, monkeypatch, capsys):
    """A single runtime can yield N bindings via the 'add another?' loop."""
    from coral.cli.agents import cmd_setup

    def fake_which(cmd):
        return "/usr/local/bin/claude" if cmd == "claude" else None

    monkeypatch.setattr("coral.agent.registry.shutil.which", fake_which)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    answers = iter(
        [
            "1",  # select runtime #1 (claude_code)
            "claude-opus",  # binding name 1
            "opus",  # model 1
            "",  # role_file 1 (skip)
            "y",  # add another?
            "claude-sonnet",  # binding name 2
            "sonnet",  # model 2
            "",  # role_file 2 (skip)
            "n",  # stop adding
        ]
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    cmd_setup(_ns(setup_command=None, non_interactive=False, config=None))

    store = load_store()
    assert {"claude-opus", "claude-sonnet"} <= set(store.bindings)
    assert store.bindings["claude-opus"].model == "opus"
    assert store.bindings["claude-sonnet"].model == "sonnet"
    # Both point at the same runtime.
    assert store.bindings["claude-opus"].runtime == "claude_code"
    assert store.bindings["claude-sonnet"].runtime == "claude_code"
    assert "Saved 2 binding(s)" in capsys.readouterr().out


def test_setup_detect_records_role_file(bindings_file, tmp_path, monkeypatch, capsys):
    """When the user supplies a role_file path it ends up on the binding."""
    from coral.cli.agents import cmd_setup

    role = tmp_path / "role.md"
    role.write_text("# generalist\n")

    monkeypatch.setattr(
        "coral.agent.registry.shutil.which",
        lambda cmd: "/usr/local/bin/claude" if cmd == "claude" else None,
    )
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    # Pick #1, accept default name, accept default model, supply role_file, no more.
    answers = iter(["1", "", "", str(role), "n"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    cmd_setup(_ns(setup_command=None, non_interactive=False, config=None))

    binding = load_store().bindings["claude-code"]
    assert binding.role_file == str(role)


def test_setup_detect_warns_on_missing_role_file(bindings_file, monkeypatch, capsys):
    """A non-existent role_file path is accepted but flagged."""
    from coral.cli.agents import cmd_setup

    monkeypatch.setattr(
        "coral.agent.registry.shutil.which",
        lambda cmd: "/usr/local/bin/claude" if cmd == "claude" else None,
    )
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    answers = iter(["1", "", "", "/nope/does/not/exist.md", "n"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    cmd_setup(_ns(setup_command=None, non_interactive=False, config=None))

    binding = load_store().bindings["claude-code"]
    assert binding.role_file == "/nope/does/not/exist.md"
    out = capsys.readouterr().out
    assert "no file at /nope/does/not/exist.md" in out


def test_setup_detect_select_multiple_with_comma(bindings_file, monkeypatch, capsys):
    """Selecting '1,2' creates bindings for both runtimes in one pass."""
    from coral.cli.agents import cmd_setup

    def fake_which(cmd):
        return f"/usr/local/bin/{cmd}" if cmd in ("claude", "codex") else None

    monkeypatch.setattr("coral.agent.registry.shutil.which", fake_which)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    # Pick #1 (claude_code) and #2 (codex). For each: name, model, role_file (skip), 'n' to "add another?"
    answers = iter(["1,2", "", "", "", "n", "", "", "", "n"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    cmd_setup(_ns(setup_command=None, non_interactive=False, config=None))

    store = load_store()
    assert "claude-code" in store.bindings
    assert "codex" in store.bindings
    assert store.bindings["codex"].runtime == "codex"
    assert "Saved 2 binding(s)" in capsys.readouterr().out


def test_setup_detect_select_all_keyword(bindings_file, monkeypatch, capsys):
    """The 'all' keyword selects every detected runtime."""
    from coral.cli.agents import cmd_setup

    def fake_which(cmd):
        return f"/usr/local/bin/{cmd}" if cmd in ("claude", "codex") else None

    monkeypatch.setattr("coral.agent.registry.shutil.which", fake_which)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    answers = iter(["all", "", "", "", "n", "", "", "", "n"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    cmd_setup(_ns(setup_command=None, non_interactive=False, config=None))

    store = load_store()
    assert {"claude-code", "codex"} <= set(store.bindings)


def test_setup_detect_empty_selection_skips(bindings_file, monkeypatch, capsys):
    """Pressing Enter at the selection prompt creates no bindings."""
    from coral.cli.agents import cmd_setup

    monkeypatch.setattr(
        "coral.agent.registry.shutil.which",
        lambda cmd: "/usr/local/bin/claude" if cmd == "claude" else None,
    )
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")

    cmd_setup(_ns(setup_command=None, non_interactive=False, config=None))

    assert load_store().bindings == {}
    assert "No bindings created" in capsys.readouterr().out


def test_setup_detect_invalid_selection_reprompts(bindings_file, monkeypatch, capsys):
    """Garbage input triggers a re-prompt; eventually empty -> skip."""
    from coral.cli.agents import cmd_setup

    monkeypatch.setattr(
        "coral.agent.registry.shutil.which",
        lambda cmd: "/usr/local/bin/claude" if cmd == "claude" else None,
    )
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    answers = iter(["xyz", "99", ""])  # invalid, out-of-range, then skip
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    cmd_setup(_ns(setup_command=None, non_interactive=False, config=None))

    out = capsys.readouterr().out
    assert "not a valid selection" in out
    assert load_store().bindings == {}


def test_parse_selection_handles_ranges_and_aliases():
    from coral.cli.agents import _parse_selection

    assert _parse_selection("all", 4) == [1, 2, 3, 4]
    assert _parse_selection("", 4) == []
    assert _parse_selection("q", 4) == []
    assert _parse_selection("1,3", 4) == [1, 3]
    assert _parse_selection("1 3", 4) == [1, 3]
    assert _parse_selection("1-3", 4) == [1, 2, 3]
    assert _parse_selection("3-1", 4) == [1, 2, 3]
    assert _parse_selection("1,3,3", 4) == [1, 3]
    # invalid: non-numeric, out-of-range
    assert _parse_selection("abc", 4) is None
    assert _parse_selection("5", 4) is None
    assert _parse_selection("1-10", 4) is None


def test_setup_detect_shows_existing_binding_count(bindings_file, monkeypatch, capsys):
    """A runtime with an existing binding shows '(N binding)' in the report
    and '[N existing binding]' in the selection list, but is still selectable
    so the user can add additional bindings for that runtime.
    """
    from coral.cli.agents import cmd_setup

    # Pre-seed one binding for claude_code.
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
    capsys.readouterr()

    def fake_which(cmd):
        return "/usr/local/bin/claude" if cmd == "claude" else None

    monkeypatch.setattr("coral.agent.registry.shutil.which", fake_which)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    # Skip via empty selection.
    monkeypatch.setattr("builtins.input", lambda prompt="": "")

    cmd_setup(_ns(setup_command=None, non_interactive=False, config=None))
    out = capsys.readouterr().out
    # Top scanning report shows the existing binding count.
    assert "(1 binding)" in out
    # Selection list annotates it too.
    assert "[1 existing binding]" in out
    # Nothing new was created.
    assert set(load_store().bindings) == {"my-claude"}


def test_setup_detect_can_add_second_binding_for_already_bound_runtime(
    bindings_file, monkeypatch, capsys
):
    """Pre-bound runtimes are still selectable; a second binding gets a unique
    default name suggestion that avoids the existing one."""
    from coral.cli.agents import cmd_setup

    cmd_setup(
        _ns(
            setup_command="agent",
            name="claude-code",  # squat the obvious default name
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

    def fake_which(cmd):
        return "/usr/local/bin/claude" if cmd == "claude" else None

    monkeypatch.setattr("coral.agent.registry.shutil.which", fake_which)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    # Select #1, accept the de-duped default name (claude-code-2), accept default model, skip role_file, 'n'.
    answers = iter(["1", "", "", "", "n"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    cmd_setup(_ns(setup_command=None, non_interactive=False, config=None))

    store = load_store()
    assert {"claude-code", "claude-code-2"} <= set(store.bindings)
    assert store.bindings["claude-code-2"].runtime == "claude_code"
