"""Live bubblewrap smoke tests.

These tests require a Linux host with `bwrap` installed. They exercise the
actual mount namespace, not just command construction.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from coral.sandbox.bwrap import (
    AgentSandboxSpec,
    SubmittedCodeSandboxSpec,
    build_agent_bwrap_command,
    build_submitted_code_bwrap_command,
    sanitize_agent_env,
    sanitize_submitted_code_env,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bwrap") is None,
    reason="requires Linux/WSL with bubblewrap installed",
)


def test_live_agent_bwrap_hides_private_and_host_home(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    coral_dir = run_dir / ".coral"
    worktree = run_dir / "agents" / "agent-0"
    repo = run_dir / "repo"
    public = coral_dir / "public"
    private = coral_dir / "private"
    home = coral_dir / "agent_homes" / "agent-0" / "home"
    for path in (worktree, repo, public, private):
        path.mkdir(parents=True, exist_ok=True)
    (private / "secret.txt").write_text("hidden")
    (coral_dir / "config.yaml").write_text("task:\n  name: t\n")
    (coral_dir / "config_dir").write_text(str(tmp_path))

    script = """
from pathlib import Path
import os, sys
work_file, public_file, private_file, host_home = map(Path, sys.argv[1:])
assert not private_file.exists(), f"private visible: {private_file}"
assert not (host_home / ".codex").exists(), f"host home visible: {host_home}"
assert Path("/etc/resolv.conf").read_text().strip(), "resolv.conf target unreadable"
work_file.write_text("work")
public_file.write_text("public")
Path(os.environ["HOME"], "probe.txt").write_text("home")
"""
    spec = AgentSandboxSpec(
        bwrap_path=shutil.which("bwrap") or "bwrap",
        agent_id="agent-0",
        worktree_path=worktree,
        coral_dir=coral_dir,
        repo_dir=repo,
        state_root=public,
        home_dir=home,
        shared_dir_name=".codex",
    )
    cmd = build_agent_bwrap_command(
        [
            "python3",
            "-c",
            script,
            str(worktree / "agent.txt"),
            str(public / "note.txt"),
            str(private / "secret.txt"),
            str(Path.home()),
        ],
        spec,
    )

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=20,
        env=sanitize_agent_env(dict(os.environ)),
    )

    assert result.returncode == 0, result.stderr
    assert (worktree / "agent.txt").read_text() == "work"
    assert (public / "note.txt").read_text() == "public"
    assert (home / "probe.txt").read_text() == "home"


def test_live_agent_bwrap_launches_user_home_runtime_without_operator_home_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator_home = tmp_path / "operator_home"
    operator_codex = operator_home / ".codex"
    operator_bin = operator_home / ".local" / "bin"
    runtime_bin = operator_codex / "packages" / "standalone" / "current" / "bin"
    for path in (operator_codex, operator_bin, runtime_bin):
        path.mkdir(parents=True, exist_ok=True)
    operator_auth = operator_codex / "auth.json"
    operator_auth.write_text("operator-secret")
    (operator_codex / "config.toml").write_text("model = 'test'\n")

    fake_codex = runtime_bin / "codex"
    fake_codex.write_text(
        "#!/bin/sh\n"
        'result_file="$1"\n'
        'operator_auth="$2"\n'
        'if [ ! -f "$HOME/.codex/auth.json" ]; then\n'
        "  echo 'missing projected runtime auth' >&2\n"
        "  exit 41\n"
        "fi\n"
        'if [ -e "$operator_auth" ]; then\n'
        "  echo 'operator auth path leaked' >&2\n"
        "  exit 42\n"
        "fi\n"
        "printf 'runtime ok' > \"$result_file\"\n"
    )
    fake_codex.chmod(0o755)
    (operator_bin / "codex").symlink_to(fake_codex)

    run_dir = tmp_path / "run"
    coral_dir = run_dir / ".coral"
    worktree = run_dir / "agents" / "agent-0"
    repo = run_dir / "repo"
    public = coral_dir / "public"
    home = coral_dir / "agent_homes" / "agent-0" / "home"
    for path in (worktree, repo, public):
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HOME", str(operator_home))
    monkeypatch.setenv("PATH", f"{operator_bin}:/usr/local/bin:/usr/bin:/bin")

    spec = AgentSandboxSpec(
        bwrap_path=shutil.which("bwrap") or "bwrap",
        agent_id="agent-0",
        worktree_path=worktree,
        coral_dir=coral_dir,
        repo_dir=repo,
        state_root=public,
        home_dir=home,
        shared_dir_name=".codex",
        runtime_home_source=operator_codex,
    )
    cmd = build_agent_bwrap_command(
        [
            "codex",
            str(worktree / "runtime.txt"),
            str(operator_auth),
        ],
        spec,
    )

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=20,
        env=sanitize_agent_env(dict(os.environ)),
    )

    assert result.returncode == 0, result.stderr
    assert (worktree / "runtime.txt").read_text() == "runtime ok"


def test_live_submitted_code_bwrap_hides_grader_private(tmp_path: Path) -> None:
    codebase = tmp_path / "checkout"
    eval_logs = tmp_path / "eval_logs"
    private = tmp_path / ".coral" / "private"
    for path in (codebase, eval_logs, private):
        path.mkdir(parents=True, exist_ok=True)
    (private / "secret.txt").write_text("hidden")

    script = """
from pathlib import Path
import os, sys
workspace_file, eval_log_file, private_file = map(Path, sys.argv[1:])
assert str(workspace_file).startswith("/workspace/")
assert not private_file.exists(), f"private visible: {private_file}"
workspace_file.write_text("work")
eval_log_file.write_text("log")
assert Path(os.environ["HOME"]) == Path("/tmp")
"""
    spec = SubmittedCodeSandboxSpec(
        bwrap_path=shutil.which("bwrap") or "bwrap",
        codebase_path=codebase,
        eval_logs_dir=eval_logs,
    )
    cmd = build_submitted_code_bwrap_command(
        [
            "python3",
            "-c",
            script,
            str(codebase / "result.txt"),
            str(eval_logs / "trace.txt"),
            str(private / "secret.txt"),
        ],
        spec,
    )

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=20,
        env=sanitize_submitted_code_env(dict(os.environ)),
    )

    assert result.returncode == 0, result.stderr
    assert (codebase / "result.txt").read_text() == "work"
    assert (eval_logs / "trace.txt").read_text() == "log"
