"""Integration points for agent runtime bubblewrap sandboxing."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="CORAL runtime imports are POSIX-only"
)

from coral.agent.builtin.codex import CodexRuntime  # noqa: E402
from coral.agent.manager import AgentManager  # noqa: E402
from coral.agent.runtime import AgentHandle  # noqa: E402
from coral.config import CoralConfig  # noqa: E402
from coral.sandbox.bwrap import AgentSandboxSpec  # noqa: E402
from coral.workspace.project import ProjectPaths  # noqa: E402


class _FakePopen:
    captured: list[dict[str, Any]] = []

    def __init__(self, cmd, **kwargs) -> None:  # type: ignore[no-untyped-def]
        type(self).captured.append({"cmd": list(cmd), "kwargs": dict(kwargs)})
        self.pid = 1234
        self.returncode: int | None = None
        self.stdout = None
        self.stderr = None

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None:
        self.returncode = -9

    def terminate(self) -> None:
        self.returncode = -15


@pytest.fixture(autouse=True)
def _reset_fake_popen() -> None:
    _FakePopen.captured = []


def _sandbox_spec(tmp_path: Path, worktree: Path) -> AgentSandboxSpec:
    coral_dir = tmp_path / ".coral"
    for path in (coral_dir / "public", coral_dir / "private", tmp_path / "repo"):
        path.mkdir(parents=True, exist_ok=True)
    (coral_dir / "config.yaml").write_text("task:\n  name: t\n")
    (coral_dir / "config_dir").write_text(str(tmp_path))
    return AgentSandboxSpec(
        bwrap_path="/usr/bin/bwrap",
        agent_id="agent-1",
        worktree_path=worktree,
        coral_dir=coral_dir,
        repo_dir=tmp_path / "repo",
        state_root=coral_dir / "public",
        home_dir=coral_dir / "agent_homes" / "agent-1" / "home",
        shared_dir_name=".codex",
    )


def test_codex_runtime_wraps_subprocess_with_bwrap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(subprocess, "Popen", _FakePopen)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "host-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "agent-key")

    worktree = tmp_path / "agent-1"
    worktree.mkdir()
    (worktree / ".coral_agent_id").write_text("agent-1")
    spec = _sandbox_spec(tmp_path, worktree)

    runtime = CodexRuntime()
    runtime.start(
        worktree_path=worktree,
        coral_md_path=worktree / "AGENTS.md",
        model="gpt-5.4",
        log_dir=tmp_path / "logs",
        prompt="hello",
        sandbox_spec=spec,
    )

    captured = _FakePopen.captured[0]
    cmd = captured["cmd"]
    env = captured["kwargs"]["env"]

    assert cmd[0] == "/usr/bin/bwrap"
    assert "--chdir" in cmd
    assert str(worktree) in cmd
    assert cmd[-3:] == ["--model", "gpt-5.4", "--json"]
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert env["OPENAI_API_KEY"] == "agent-key"


def test_codex_runtime_prefers_wsl_native_binary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(subprocess, "Popen", _FakePopen)
    operator_home = tmp_path / "operator_home"
    native_codex = operator_home / ".local" / "bin" / "codex"
    native_codex.parent.mkdir(parents=True)
    native_codex.write_text("#!/bin/sh\n")
    monkeypatch.setenv("HOME", str(operator_home))
    monkeypatch.setenv("PATH", "/mnt/c/Users/example/AppData/Roaming/npm:/usr/bin")

    worktree = tmp_path / "agent-1"
    worktree.mkdir()
    (worktree / ".coral_agent_id").write_text("agent-1")

    CodexRuntime().start(
        worktree_path=worktree,
        coral_md_path=worktree / "AGENTS.md",
        model="gpt-5.4",
        log_dir=tmp_path / "logs",
        prompt="hello",
    )

    assert _FakePopen.captured[0]["cmd"][0] == str(native_codex)


def test_codex_runtime_command_option_overrides_default_binary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(subprocess, "Popen", _FakePopen)
    operator_home = tmp_path / "operator_home"
    native_codex = operator_home / ".local" / "bin" / "codex"
    native_codex.parent.mkdir(parents=True)
    native_codex.write_text("#!/bin/sh\n")
    monkeypatch.setenv("HOME", str(operator_home))

    worktree = tmp_path / "agent-1"
    worktree.mkdir()
    (worktree / ".coral_agent_id").write_text("agent-1")

    CodexRuntime().start(
        worktree_path=worktree,
        coral_md_path=worktree / "AGENTS.md",
        model="gpt-5.4",
        runtime_options={"command": "/opt/codex/bin/codex"},
        log_dir=tmp_path / "logs",
        prompt="hello",
    )

    assert _FakePopen.captured[0]["cmd"][0] == "/opt/codex/bin/codex"


class _RecordingRuntime:
    instruction_filename = "AGENTS.md"
    shared_dir_name = ".codex"

    def __init__(self) -> None:
        self.sandbox_spec: AgentSandboxSpec | None = None

    def start(self, **kwargs: Any) -> AgentHandle:
        self.sandbox_spec = kwargs.get("sandbox_spec")
        return AgentHandle(
            agent_id="agent-1",
            process=None,
            worktree_path=kwargs["worktree_path"],
            log_path=kwargs["log_dir"] / "agent-1.0.log",
        )

    def extract_session_id(self, log_path: Path) -> str | None:
        return None


def test_manager_resolves_and_passes_agent_sandbox_spec(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import coral.agent.manager as manager_mod
    import coral.sandbox.bwrap as bwrap_mod

    cfg = CoralConfig()
    cfg.task.name = "t"
    cfg.task.description = "d"
    cfg.agents.runtime = "codex"
    cfg.run.sandbox.mode = "required"

    coral_dir = tmp_path / ".coral"
    public = coral_dir / "public"
    for sub in ("attempts", "logs", "skills", "agents", "notes", "heartbeat", "eval_logs", "roles"):
        (public / sub).mkdir(parents=True, exist_ok=True)
    (coral_dir / "private").mkdir(parents=True)
    (coral_dir / "config.yaml").write_text("task:\n  name: t\n")
    (coral_dir / "config_dir").write_text(str(tmp_path))
    repo_dir = tmp_path / "repo"
    agents_dir = tmp_path / "agents"
    repo_dir.mkdir()
    agents_dir.mkdir()
    worktree = agents_dir / "agent-1"
    worktree.mkdir()

    manager = AgentManager(cfg)
    manager.paths = ProjectPaths(
        results_dir=tmp_path,
        task_dir=tmp_path,
        run_dir=tmp_path,
        coral_dir=coral_dir,
        agents_dir=agents_dir,
        repo_dir=repo_dir,
    )
    runtime = _RecordingRuntime()
    manager.runtimes["agent-1"] = runtime  # type: ignore[assignment]

    monkeypatch.setattr(manager_mod, "create_agent_worktree", lambda *args, **kwargs: worktree)
    monkeypatch.setattr(manager_mod, "setup_worktree_env", lambda *args, **kwargs: None)
    monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: "/usr/bin/bwrap")
    monkeypatch.delenv("CORAL_IN_DOCKER", raising=False)

    handle = manager._setup_and_start_agent("agent-1")

    assert handle.agent_id == "agent-1"
    assert runtime.sandbox_spec is not None
    assert runtime.sandbox_spec.worktree_path == worktree
    assert runtime.sandbox_spec.state_root == coral_dir / "public"
    assert runtime.sandbox_spec.home_dir == coral_dir / "agent_homes" / "agent-1" / "home"
