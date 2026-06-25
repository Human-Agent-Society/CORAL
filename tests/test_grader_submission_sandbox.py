"""Tests for sandboxing submitted-code subprocesses launched by graders."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from coral.config import CoralConfig, GraderConfig
from coral.grader.task_grader import TaskGrader
from coral.sandbox.bwrap import SandboxUnavailable


class _NoopGrader(TaskGrader):
    def evaluate(self) -> float:
        return 0.0


def _grader(tmp_path: Path, config: GraderConfig) -> _NoopGrader:
    coral_dir = tmp_path / ".coral"
    private_dir = coral_dir / "private"
    codebase = coral_dir / "private" / "grader_checkouts" / "abc123"
    codebase.mkdir(parents=True)
    private_dir.mkdir(parents=True, exist_ok=True)
    g = _NoopGrader(config=config)
    g.private_dir = str(private_dir)
    g.codebase_path = str(codebase)
    g.island_id = None
    return g


def _fake_run(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return captured


def _bind_pairs(cmd: list[str], flag: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(cmd):
        if cmd[i] == flag:
            pairs.append((cmd[i + 1], cmd[i + 2]))
            i += 3
            continue
        i += 1
    return pairs


def test_config_accepts_grader_submission_sandbox_section() -> None:
    cfg = CoralConfig.from_dict(
        {
            "task": {"name": "t", "description": "d"},
            "grader": {
                "sandbox": {
                    "mode": "required",
                    "backend": "bwrap",
                    "profile": "private-safe",
                }
            },
        }
    )

    assert cfg.grader.sandbox.mode == "required"
    assert cfg.grader.sandbox.backend == "bwrap"
    assert cfg.grader.sandbox.profile == "private-safe"


def test_run_program_wraps_submitted_code_with_bwrap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    captured = _fake_run(monkeypatch)
    grader = _grader(
        tmp_path,
        GraderConfig(sandbox={"mode": "required", "backend": "bwrap"}),
    )
    (Path(grader.codebase_path) / "solution.py").write_text("print('ok')")

    result = grader.run_program("solution.py", "--case", "1")

    cmd = captured["cmd"]
    rendered = "\n".join(cmd)
    assert result.stdout == "ok"
    assert cmd[0] == "/usr/bin/bwrap"
    assert "--chdir" in cmd
    assert "/workspace" in rendered
    assert (str(grader.private_dir), str(grader.private_dir)) not in _bind_pairs(cmd, "--bind")
    assert cmd[-3:] == ["/workspace/solution.py", "--case", "1"]


def test_run_program_projects_user_installed_uv_into_submitted_code_sandbox(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    user_bin = tmp_path / "home" / ".local" / "bin"
    user_bin.mkdir(parents=True)
    uv_bin = user_bin / "uv"
    uv_bin.write_text("#!/bin/sh\n")
    uv_bin.chmod(0o755)

    def fake_which(name: str) -> str | None:
        if name == "bwrap":
            return "/usr/bin/bwrap"
        if name == "uv":
            return str(uv_bin)
        return None

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setenv("PATH", str(user_bin))
    captured = _fake_run(monkeypatch)
    grader = _grader(
        tmp_path,
        GraderConfig(sandbox={"mode": "required", "backend": "bwrap"}),
    )
    (Path(grader.codebase_path) / "pyproject.toml").write_text("[project]\nname = 't'\n")
    (Path(grader.codebase_path) / "solution.py").write_text("print('ok')")

    grader.run_program("solution.py")

    cmd = captured["cmd"]
    assert ("--ro-bind", str(uv_bin), str(uv_bin)) in zip(cmd, cmd[1:], cmd[2:])


def test_run_script_uses_submitted_code_sandbox(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    captured = _fake_run(monkeypatch)
    grader = _grader(
        tmp_path,
        GraderConfig(sandbox={"mode": "required", "backend": "bwrap"}),
    )

    grader.run_script("print('ok')")

    cmd = captured["cmd"]
    rendered = "\n".join(cmd)
    assert cmd[0] == "/usr/bin/bwrap"
    assert "/workspace" in rendered
    assert (str(grader.private_dir), str(grader.private_dir)) not in _bind_pairs(cmd, "--bind")
    assert cmd[-2:] == ["-c", "print('ok')"]


def test_private_grader_submission_fails_closed_without_bwrap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    grader = _grader(
        tmp_path,
        GraderConfig(private=["taskdata"]),
    )
    (Path(grader.codebase_path) / "solution.py").write_text("print('ok')")

    with pytest.raises(SandboxUnavailable, match="grader.private|submitted code"):
        grader.run_program("solution.py")


def test_non_private_auto_submission_keeps_legacy_path_without_bwrap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    captured = _fake_run(monkeypatch)
    grader = _grader(tmp_path, GraderConfig())
    (Path(grader.codebase_path) / "solution.py").write_text("print('ok')")

    grader.run_program("solution.py")

    assert captured["cmd"][0] != "/usr/bin/bwrap"
