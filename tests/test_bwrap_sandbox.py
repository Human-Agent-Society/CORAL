"""Tests for WSL/Linux-native bubblewrap sandbox planning."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from coral.config import CoralConfig
from coral.sandbox.bwrap import (
    AgentSandboxSpec,
    SandboxUnavailable,
    build_agent_bwrap_command,
    resolve_agent_sandbox,
    sanitize_agent_env,
)


def _paths(tmp_path: Path) -> SimpleNamespace:
    run_dir = tmp_path / "run"
    coral_dir = run_dir / ".coral"
    repo_dir = run_dir / "repo"
    agents_dir = run_dir / "agents"
    for path in (
        coral_dir / "public",
        coral_dir / "private",
        repo_dir,
        agents_dir / "agent-0",
    ):
        path.mkdir(parents=True, exist_ok=True)
    (coral_dir / "config.yaml").write_text("task:\n  name: t\n")
    (coral_dir / "config_dir").write_text(str(tmp_path / "task"))
    return SimpleNamespace(
        results_dir=tmp_path / "results",
        task_dir=tmp_path / "results" / "t",
        run_dir=run_dir,
        coral_dir=coral_dir,
        agents_dir=agents_dir,
        repo_dir=repo_dir,
    )


def test_config_accepts_sandbox_section() -> None:
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "run": {
                "sandbox": {
                    "mode": "required",
                    "backend": "bwrap",
                    "profile": "private-safe",
                }
            },
        }
    )

    assert cfg.run.sandbox.mode == "required"
    assert cfg.run.sandbox.backend == "bwrap"
    assert cfg.run.sandbox.profile == "private-safe"


def test_required_bwrap_fails_closed_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import coral.sandbox.bwrap as bwrap_mod

    monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: None)
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "run": {"sandbox": {"mode": "required", "backend": "bwrap"}},
        }
    )

    with pytest.raises(SandboxUnavailable, match="bubblewrap|bwrap"):
        resolve_agent_sandbox(
            cfg,
            paths=_paths(tmp_path),
            agent_id="agent-0",
            runtime_name="codex",
            shared_dir_name=".codex",
            island_id=None,
            bwrap_path=None,
            in_coral_docker=False,
        )


def test_private_data_makes_auto_mode_fail_closed_without_bwrap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import coral.sandbox.bwrap as bwrap_mod

    monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: None)
    cfg = CoralConfig()
    cfg.task.name = "t"
    cfg.task.description = "d"
    cfg.grader.entrypoint = "pkg:Grader"
    cfg.grader.private = ["taskdata"]
    cfg.agents.runtime = "codex"

    with pytest.raises(SandboxUnavailable, match="grader.private"):
        resolve_agent_sandbox(
            cfg,
            paths=_paths(tmp_path),
            agent_id="agent-0",
            runtime_name="codex",
            shared_dir_name=".codex",
            island_id=None,
            bwrap_path=None,
            in_coral_docker=False,
        )


def test_private_data_rejects_local_agent_sandbox_opt_out(tmp_path: Path) -> None:
    cfg = CoralConfig()
    cfg.task.name = "t"
    cfg.task.description = "d"
    cfg.grader.private = ["taskdata"]
    cfg.run.sandbox.mode = "off"

    with pytest.raises(SandboxUnavailable, match="grader.private"):
        resolve_agent_sandbox(
            cfg,
            paths=_paths(tmp_path),
            agent_id="agent-0",
            runtime_name="codex",
            shared_dir_name=".codex",
            island_id=None,
            bwrap_path="/usr/bin/bwrap",
            in_coral_docker=False,
        )


def test_docker_session_allows_sandbox_off_for_private_data(tmp_path: Path) -> None:
    cfg = CoralConfig()
    cfg.task.name = "t"
    cfg.task.description = "d"
    cfg.grader.private = ["taskdata"]
    cfg.run.sandbox.mode = "off"
    cfg.run.session = "docker"

    spec = resolve_agent_sandbox(
        cfg,
        paths=_paths(tmp_path),
        agent_id="agent-0",
        runtime_name="codex",
        shared_dir_name=".codex",
        island_id=None,
        bwrap_path=None,
        in_coral_docker=True,
    )

    assert spec is None


def test_auto_mode_uses_bwrap_for_full_access_codex_when_available(tmp_path: Path) -> None:
    cfg = CoralConfig()
    cfg.task.name = "t"
    cfg.task.description = "d"
    cfg.agents.runtime = "codex"

    spec = resolve_agent_sandbox(
        cfg,
        paths=_paths(tmp_path),
        agent_id="agent-0",
        runtime_name="codex",
        shared_dir_name=".codex",
        island_id=None,
        bwrap_path="/usr/bin/bwrap",
        in_coral_docker=False,
    )

    assert spec is not None
    assert spec.bwrap_path == "/usr/bin/bwrap"
    assert spec.home_dir.name == "home"
    assert spec.state_root.name == "public"


def test_auto_mode_keeps_legacy_path_when_full_access_runtime_has_no_bwrap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import coral.sandbox.bwrap as bwrap_mod

    monkeypatch.setattr(bwrap_mod.shutil, "which", lambda name: None)
    cfg = CoralConfig()
    cfg.task.name = "t"
    cfg.task.description = "d"
    cfg.agents.runtime = "codex"

    spec = resolve_agent_sandbox(
        cfg,
        paths=_paths(tmp_path),
        agent_id="agent-0",
        runtime_name="codex",
        shared_dir_name=".codex",
        island_id=None,
        bwrap_path=None,
        in_coral_docker=False,
    )

    assert spec is None


@pytest.mark.parametrize("runtime_name", ["pi", "cursor", "cursor_agent"])
def test_auto_mode_uses_bwrap_for_full_access_runtime_aliases(
    tmp_path: Path,
    runtime_name: str,
) -> None:
    cfg = CoralConfig()
    cfg.task.name = "t"
    cfg.task.description = "d"

    spec = resolve_agent_sandbox(
        cfg,
        paths=_paths(tmp_path),
        agent_id="agent-0",
        runtime_name=runtime_name,
        shared_dir_name=".codex",
        island_id=None,
        bwrap_path="/usr/bin/bwrap",
        in_coral_docker=False,
    )

    assert spec is not None


def test_auto_mode_preserves_custom_runtime_compatibility(tmp_path: Path) -> None:
    cfg = CoralConfig()
    cfg.task.name = "t"
    cfg.task.description = "d"

    spec = resolve_agent_sandbox(
        cfg,
        paths=_paths(tmp_path),
        agent_id="agent-0",
        runtime_name="my_pkg.runtime:Runtime",
        shared_dir_name=".custom",
        island_id=None,
        bwrap_path="/usr/bin/bwrap",
        in_coral_docker=False,
    )

    assert spec is None


def test_docker_session_does_not_stack_bwrap(tmp_path: Path) -> None:
    cfg = CoralConfig()
    cfg.task.name = "t"
    cfg.task.description = "d"
    cfg.grader.entrypoint = "pkg:Grader"
    cfg.grader.private = ["taskdata"]
    cfg.agents.runtime = "codex"

    spec = resolve_agent_sandbox(
        cfg,
        paths=_paths(tmp_path),
        agent_id="agent-0",
        runtime_name="codex",
        shared_dir_name=".codex",
        island_id=None,
        bwrap_path=None,
        in_coral_docker=True,
    )

    assert spec is None


def test_bwrap_command_projects_public_state_without_private(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    spec = AgentSandboxSpec(
        bwrap_path="/usr/bin/bwrap",
        agent_id="agent-0",
        worktree_path=paths.agents_dir / "agent-0",
        coral_dir=paths.coral_dir,
        repo_dir=paths.repo_dir,
        state_root=paths.coral_dir / "public",
        home_dir=paths.coral_dir / "agent_homes" / "agent-0" / "home",
        shared_dir_name=".codex",
    )

    wrapped = build_agent_bwrap_command(["codex", "exec", "hello"], spec)
    rendered = "\n".join(wrapped)

    assert wrapped[0] == "/usr/bin/bwrap"
    assert "--chdir" in wrapped
    assert str(spec.worktree_path) in rendered
    assert str(spec.repo_dir) in rendered
    assert str(spec.state_root) in rendered
    assert str(spec.coral_dir / "config.yaml") in rendered
    assert str(spec.coral_dir / "config_dir") in rendered
    assert str(spec.coral_dir / "private") not in rendered
    assert wrapped[-3:] == ["codex", "exec", "hello"]


def test_bwrap_command_projects_user_home_runtime_executable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    operator_home = tmp_path / "operator_home"
    operator_bin = operator_home / ".local" / "bin"
    runtime_bin = operator_home / ".codex" / "packages" / "standalone" / "current" / "bin"
    operator_bin.mkdir(parents=True)
    runtime_bin.mkdir(parents=True)
    real_codex = runtime_bin / "codex"
    real_codex.write_text("#!/bin/sh\n")
    real_codex.chmod(0o755)
    shim_codex = operator_bin / "codex"
    shim_codex.symlink_to(real_codex)
    monkeypatch.setenv("PATH", str(operator_bin))

    paths = _paths(tmp_path)
    spec = AgentSandboxSpec(
        bwrap_path="/usr/bin/bwrap",
        agent_id="agent-0",
        worktree_path=paths.agents_dir / "agent-0",
        coral_dir=paths.coral_dir,
        repo_dir=paths.repo_dir,
        state_root=paths.coral_dir / "public",
        home_dir=paths.coral_dir / "agent_homes" / "agent-0" / "home",
        shared_dir_name=".codex",
    )

    wrapped = build_agent_bwrap_command(["codex", "exec", "hello"], spec)

    assert "--ro-bind" in wrapped
    assert str(real_codex.resolve()) in wrapped
    assert str(shim_codex) in wrapped


def test_bwrap_command_projects_runtime_home_allowlisted_files(tmp_path: Path) -> None:
    operator_home = tmp_path / "operator_home"
    operator_codex = operator_home / ".codex"
    operator_codex.mkdir(parents=True)
    (operator_codex / "auth.json").write_text("auth")
    (operator_codex / "config.toml").write_text("config")
    (operator_codex / "unrelated-token.txt").write_text("do-not-copy")
    (operator_codex / "sessions").mkdir()
    (operator_codex / "sessions" / "old.jsonl").write_text("large-session-history")

    paths = _paths(tmp_path)
    spec = AgentSandboxSpec(
        bwrap_path="/usr/bin/bwrap",
        agent_id="agent-0",
        worktree_path=paths.agents_dir / "agent-0",
        coral_dir=paths.coral_dir,
        repo_dir=paths.repo_dir,
        state_root=paths.coral_dir / "public",
        home_dir=paths.coral_dir / "agent_homes" / "agent-0" / "home",
        shared_dir_name=".codex",
        runtime_home_source=operator_codex,
    )

    build_agent_bwrap_command(["codex", "exec", "hello"], spec)

    projected = spec.home_dir / ".codex"
    assert (projected / "auth.json").read_text() == "auth"
    assert (projected / "config.toml").read_text() == "config"
    assert not (projected / "unrelated-token.txt").exists()
    assert not (projected / "sessions" / "old.jsonl").exists()


def test_bwrap_command_projects_coral_source_root_read_only(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    coral_source = tmp_path / "coral-src"
    (coral_source / "coral").mkdir(parents=True)
    (coral_source / "pyproject.toml").write_text("[project]\nname = 'coral'\n")
    spec = AgentSandboxSpec(
        bwrap_path="/usr/bin/bwrap",
        agent_id="agent-0",
        worktree_path=paths.agents_dir / "agent-0",
        coral_dir=paths.coral_dir,
        repo_dir=paths.repo_dir,
        state_root=paths.coral_dir / "public",
        home_dir=paths.coral_dir / "agent_homes" / "agent-0" / "home",
        shared_dir_name=".codex",
        coral_source_root=coral_source,
    )

    wrapped = build_agent_bwrap_command(["codex", "exec", "hello"], spec)

    bind_at = [
        idx
        for idx, item in enumerate(wrapped)
        if item == "--ro-bind"
        and idx + 2 < len(wrapped)
        and wrapped[idx + 1] == str(coral_source)
        and wrapped[idx + 2] == str(coral_source)
    ]
    assert bind_at


def test_sanitize_agent_env_keeps_only_runtime_safe_keys() -> None:
    env = {
        "PATH": "/usr/bin",
        "LANG": "C.UTF-8",
        "OPENAI_API_KEY": "agent-key",
        "AWS_SECRET_ACCESS_KEY": "host-secret",
        "RANDOM_TOKEN": "host-token",
        "VIRTUAL_ENV": "/work/.venv",
    }

    filtered = sanitize_agent_env(env, extra_allowed_keys={"OPENAI_API_KEY"})

    assert filtered["PATH"] == "/usr/bin"
    assert filtered["OPENAI_API_KEY"] == "agent-key"
    assert filtered["VIRTUAL_ENV"] == "/work/.venv"
    assert "AWS_SECRET_ACCESS_KEY" not in filtered
    assert "RANDOM_TOKEN" not in filtered
