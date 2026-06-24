"""OS-user isolation is mandatory (not a tunable) in CORAL's Docker session."""

from __future__ import annotations

import ast
import inspect
import textwrap
from types import SimpleNamespace

import pytest

import coral.cli.start as start_mod
from coral.cli._helpers import in_coral_docker_session
from coral.cli.start import _enforce_docker_isolation
from coral.config import CoralConfig
from coral.workspace.user_isolation import DOCKER_ISOLATION_USER


def _config(isolate_user: str) -> CoralConfig:
    cfg = CoralConfig()
    cfg.agents.isolate_user = isolate_user
    return cfg


def test_in_coral_docker_session_keys_on_env(monkeypatch):
    monkeypatch.delenv("CORAL_IN_DOCKER", raising=False)
    assert in_coral_docker_session() is False
    monkeypatch.setenv("CORAL_IN_DOCKER", "1")
    assert in_coral_docker_session() is True
    # A generic container marker alone must NOT count as CORAL's session.
    monkeypatch.setenv("CORAL_IN_DOCKER", "0")
    assert in_coral_docker_session() is False


def test_host_isolation_stays_opt_in(monkeypatch):
    monkeypatch.delenv("CORAL_IN_DOCKER", raising=False)

    cfg = _config("")
    _enforce_docker_isolation(cfg)
    assert cfg.agents.isolate_user == ""  # no-op: opt-out preserved

    cfg = _config("alice")
    _enforce_docker_isolation(cfg)
    assert cfg.agents.isolate_user == "alice"  # no-op: host value preserved


@pytest.mark.parametrize("requested", ["", "alice", "root", DOCKER_ISOLATION_USER])
def test_docker_session_forces_isolation(monkeypatch, requested):
    """Inside CORAL's Docker session isolation is forced on regardless of input.

    Covers the opt-out attempt (``agents.isolate_user=``) and any alternate user
    a CLI override might try to slip in — all collapse to the image's user.
    """
    monkeypatch.setenv("CORAL_IN_DOCKER", "1")
    cfg = _config(requested)
    _enforce_docker_isolation(cfg)
    assert cfg.agents.isolate_user == DOCKER_ISOLATION_USER


# --- Wiring tests: the pure helper is correct, but isolation is only mandatory
# if the entrypoints actually call it. These guard against the call site being
# removed (which silently re-enables the user opt-out) — a regression the unit
# tests above cannot see because they invoke the helper directly. ---


def _calls_enforce(func) -> bool:
    """True if ``func``'s body contains a direct _enforce_docker_isolation call."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_enforce_docker_isolation"
        for node in ast.walk(tree)
    )


def test_both_entrypoints_wire_enforcement():
    # Removing the call from either path re-opens the opt-out the helper closes.
    assert _calls_enforce(start_mod.cmd_start), "cmd_start must enforce docker isolation"
    assert _calls_enforce(start_mod.cmd_resume), "cmd_resume must enforce docker isolation"


def test_start_in_docker_injects_no_removable_override():
    # The host-side docker launcher must NOT pass agents.isolate_user as a CLI
    # override — that was the removable opt-out. Enforcement now happens inside
    # the container, so the launcher must not reference the knob at all.
    assert "isolate_user" not in inspect.getsource(start_mod._start_in_docker)


def test_cmd_start_forces_isolation_despite_override(monkeypatch, tmp_path):
    """End-to-end: CORAL_IN_DOCKER=1 + a CLI override trying to set a different
    isolation user still reaches the manager pinned to the image's user.

    Drives cmd_start through the real override-merge + _enforce_docker_isolation
    path, capturing the config the manager is constructed with. Catches both a
    removed call site and any way an override could bypass the boundary.
    """
    monkeypatch.setenv("CORAL_IN_DOCKER", "1")

    base = CoralConfig()
    base.task.name = "t"  # mandatory fields; needed for the override-merge to resolve
    base.task.description = "t"
    base.run.session = "local"  # inner-process mode; skip the docker/tmux dispatch
    monkeypatch.setattr(start_mod.CoralConfig, "from_yaml", classmethod(lambda cls, path: base))
    monkeypatch.setattr(start_mod, "in_tmux", lambda: False)
    monkeypatch.setattr("coral.cli.validation.validate_task", lambda task_dir: [])

    captured = {}

    class FakeManager:
        def __init__(self, config, verbose=False, config_dir=None):
            captured["config"] = config
            self.specs = []
            self.paths = SimpleNamespace(run_dir=tmp_path, coral_dir=tmp_path / ".coral")

        def start_all(self):
            return []

        def monitor_loop(self):
            pass

        def wait_for_completion(self):
            pass

    monkeypatch.setattr("coral.agent.manager.AgentManager", FakeManager)

    args = SimpleNamespace(
        config=str(tmp_path / "task.yaml"),
        overrides=["agents.isolate_user=alice"],  # user attempts an alternate user
    )
    start_mod.cmd_start(args)

    assert captured["config"].agents.isolate_user == DOCKER_ISOLATION_USER
