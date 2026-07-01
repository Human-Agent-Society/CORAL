"""`coral start` must persist the session mode the user actually asked for.

The tmux/docker wrappers relaunch an inner process with ``run.session=local``
(to avoid recursion) and pass ``--wrapped-session`` so the inner process can
restore the real mode into the saved config. That restore must key on the
explicit marker — NOT ``in_tmux()``/``in_docker()`` — otherwise a user who runs
``run.session=local`` from their own tmux session or container silently gets
``tmux``/``docker`` persisted, and ``coral resume`` re-launches in the wrong
wrapper.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import coral.cli.start as start_mod
from coral.config import CoralConfig


def _drive_cmd_start(monkeypatch, tmp_path, *, session, wrapped_session, in_tmux, in_docker):
    """Run cmd_start through the real restore path, returning the config the
    manager was constructed with."""
    base = CoralConfig()
    base.task.name = "t"
    base.task.description = "t"
    base.run.session = session

    monkeypatch.setattr(start_mod.CoralConfig, "from_yaml", classmethod(lambda cls, path: base))
    monkeypatch.setattr(start_mod, "in_tmux", lambda: in_tmux)
    monkeypatch.setattr(start_mod, "in_docker", lambda: in_docker)
    monkeypatch.setattr(start_mod, "has_tmux", lambda: True)
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
        overrides=[],
        wrapped_session=wrapped_session,
    )
    start_mod.cmd_start(args)
    return captured["config"]


def test_local_from_users_own_tmux_stays_local(monkeypatch, tmp_path):
    """The reported bug: run.session=local launched from inside the user's own
    tmux (no wrapper) must NOT be rewritten to tmux."""
    config = _drive_cmd_start(
        monkeypatch,
        tmp_path,
        session="local",
        wrapped_session=None,
        in_tmux=True,
        in_docker=False,
    )
    assert config.run.session == "local"


def test_tmux_wrapper_restores_tmux(monkeypatch, tmp_path):
    """The inner process launched by the tmux wrapper (session=local +
    --wrapped-session tmux) restores tmux so resume re-launches in tmux."""
    config = _drive_cmd_start(
        monkeypatch,
        tmp_path,
        session="local",
        wrapped_session="tmux",
        in_tmux=True,
        in_docker=False,
    )
    assert config.run.session == "tmux"


def test_docker_wrapper_restores_docker(monkeypatch, tmp_path):
    config = _drive_cmd_start(
        monkeypatch,
        tmp_path,
        session="local",
        wrapped_session="docker",
        in_tmux=False,
        in_docker=True,
    )
    assert config.run.session == "docker"


def test_plain_local_stays_local(monkeypatch, tmp_path):
    config = _drive_cmd_start(
        monkeypatch,
        tmp_path,
        session="local",
        wrapped_session=None,
        in_tmux=False,
        in_docker=False,
    )
    assert config.run.session == "local"


@pytest.mark.parametrize("mode", ["tmux", "docker"])
def test_wrappers_pass_wrapped_session_flag(mode):
    """The wrappers must actually emit --wrapped-session <mode> so the inner
    process can restore it. Guards against a wrapper dropping the marker."""
    import inspect

    if mode == "tmux":
        src = inspect.getsource(start_mod._build_coral_command)
    else:
        src = inspect.getsource(start_mod._start_in_docker)
    assert "--wrapped-session" in src
    assert f'"{mode}"' in src
