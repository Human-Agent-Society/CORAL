"""Red-team smoke test for the CORAL manager -> agent bwrap path."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from coral.agent.manager import AgentManager
from coral.agent.runtime import AgentHandle, apply_agent_sandbox
from coral.config import CoralConfig
from coral.sandbox.bwrap import AgentSandboxSpec, sanitize_agent_env
from coral.workspace.project import ProjectPaths

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bwrap") is None,
    reason="requires Linux/WSL with bubblewrap installed",
)


class _RedTeamRuntime:
    instruction_filename = "AGENTS.md"
    shared_dir_name = ".codex"

    def start(
        self,
        *,
        worktree_path: Path,
        log_dir: Path,
        sandbox_spec: AgentSandboxSpec | None = None,
        **_: Any,
    ) -> AgentHandle:
        log_path = log_dir / "redteam.log"
        log_file = open(log_path, "w", buffering=1)
        report_path = sandbox_spec.state_root / "redteam-report.json"  # type: ignore[union-attr]
        parent_probe = worktree_path.parent / "sibling-secret.txt"
        script = r"""
from pathlib import Path
import json, os, sys

report_path, parent_probe = map(Path, sys.argv[1:3])
worktree = Path.cwd()
coral_dir = Path((worktree / ".coral_dir").read_text().strip())
private_secret = coral_dir / "private" / "red-secret.txt"
operator_home = Path(sys.argv[3])

checks = {
    "cwd": str(worktree),
    "home": os.environ.get("HOME"),
    "private_exists": private_secret.exists(),
    "private_read": False,
    "parent_probe_exists": parent_probe.exists(),
    "host_home_codex_exists": (operator_home / ".codex").exists(),
    "public_write": False,
}
try:
    private_secret.read_text()
    checks["private_read"] = True
except OSError:
    checks["private_read"] = False

checks["public_write"] = True
report_path.write_text(json.dumps(checks, sort_keys=True))
print(json.dumps(checks, sort_keys=True))
"""
        cmd = [
            "python3",
            "-c",
            script,
            str(report_path),
            str(parent_probe),
            str(Path.home()),
        ]
        env = sanitize_agent_env(dict(os.environ))
        cmd = apply_agent_sandbox(cmd, env, sandbox_spec)
        process = subprocess.Popen(
            cmd,
            cwd=str(worktree_path),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        return AgentHandle(
            agent_id="agent-1",
            process=process,
            worktree_path=worktree_path,
            log_path=log_path,
            _log_file=log_file,
        )

    def extract_session_id(self, log_path: Path) -> str | None:
        return None


def test_manager_launched_agent_cannot_redteam_private_or_parent_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import coral.agent.manager as manager_mod

    cfg = CoralConfig()
    cfg.task.name = "t"
    cfg.task.description = "d"
    cfg.agents.runtime = "codex"
    cfg.agents.model = "gpt-5.4"
    cfg.grader.private = ["red-secret.txt"]
    cfg.run.sandbox.mode = "required"

    run_dir = tmp_path / "run"
    coral_dir = run_dir / ".coral"
    public = coral_dir / "public"
    for sub in ("attempts", "logs", "skills", "agents", "notes", "heartbeat", "eval_logs", "roles"):
        (public / sub).mkdir(parents=True, exist_ok=True)
    private = coral_dir / "private"
    private.mkdir(parents=True)
    (private / "red-secret.txt").write_text("hidden")
    (coral_dir / "config.yaml").write_text("task:\n  name: t\n")
    (coral_dir / "config_dir").write_text(str(tmp_path))
    repo_dir = run_dir / "repo"
    agents_dir = run_dir / "agents"
    repo_dir.mkdir(parents=True)
    agents_dir.mkdir(parents=True)
    worktree = agents_dir / "agent-1"
    worktree.mkdir()
    (agents_dir / "sibling-secret.txt").write_text("sibling hidden")

    manager = AgentManager(cfg)
    manager.paths = ProjectPaths(
        results_dir=tmp_path,
        task_dir=tmp_path,
        run_dir=run_dir,
        coral_dir=coral_dir,
        agents_dir=agents_dir,
        repo_dir=repo_dir,
    )
    manager.runtimes["agent-1"] = _RedTeamRuntime()  # type: ignore[assignment]

    monkeypatch.setattr(manager_mod, "create_agent_worktree", lambda *args, **kwargs: worktree)
    monkeypatch.setattr(manager_mod, "setup_worktree_env", lambda *args, **kwargs: None)
    monkeypatch.delenv("CORAL_IN_DOCKER", raising=False)

    handle = manager._setup_and_start_agent("agent-1")
    assert handle.process is not None
    rc = handle.process.wait(timeout=20)
    assert rc == 0, handle.log_path.read_text()

    report = json.loads((public / "redteam-report.json").read_text())
    assert report["private_exists"] is False
    assert report["private_read"] is False
    assert report["parent_probe_exists"] is False
    assert report["host_home_codex_exists"] is False
    assert report["public_write"] is True
    assert report["home"].endswith("/.coral/agent_homes/agent-1/home")
