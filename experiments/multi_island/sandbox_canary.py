#!/usr/bin/env python3
"""Exercise the multi-island SRT boundary with a real ``coral eval``.

The static research preflight verifies the generated policy.  This canary
adds an executable integration check: an Avalon worktree must be able to
write its own island and submit an attempt while reads and writes against
Atlantis state and its worktree fail at the OS boundary.

Canary directories are deliberately retained under ``/var/tmp`` (or an
explicit ``--output-dir``) so a failure can be audited rather than erased.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from coral.config import CoralConfig
from coral.hub.checkpoint import init_checkpoint_repo
from coral.sandbox.protocol import AgentSandboxContext
from coral.sandbox.srt import SrtSandbox
from coral.workspace.worktree import (
    create_agent_worktree,
    setup_git_exclude,
    setup_shared_state,
    write_agent_id,
    write_coral_dir,
)

ISLANDS = ("avalon", "atlantis")
STATE_DIRS = (
    "attempts",
    "notes",
    "skills",
    "agents",
    "roles",
    "heartbeat",
    "eval_logs",
    "logs",
)


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        rendered = " ".join(command)
        raise RuntimeError(
            f"command failed ({result.returncode}): {rendered}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def _init_source_repo(source: Path) -> None:
    source.mkdir(parents=True)
    _run(["git", "init", "-b", "main"], cwd=source)
    _run(["git", "config", "user.name", "CORAL Canary"], cwd=source)
    _run(["git", "config", "user.email", "canary@coral.local"], cwd=source)
    (source / "candidate.txt").write_text("seed\n")
    _run(["git", "add", "candidate.txt"], cwd=source)
    _run(["git", "commit", "-m", "seed canary"], cwd=source)


def _build_state(coral_dir: Path) -> None:
    (coral_dir / "public").mkdir(parents=True)
    (coral_dir / "private").mkdir(parents=True)
    for island in ISLANDS:
        state = coral_dir / "islands" / island
        for relative in STATE_DIRS:
            (state / relative).mkdir(parents=True, exist_ok=True)
        init_checkpoint_repo(str(coral_dir), island_id=island)
        (state / "notes" / "marker.txt").write_text(f"{island}-state\n")


def _configure(coral_dir: Path, root: Path, source: Path) -> CoralConfig:
    config = CoralConfig.from_dict(
        {
            "task": {
                "name": "multi-island-sandbox-canary",
                "description": "Executable SRT island isolation canary",
            },
            "islands": {"count": 2},
            "agents": {
                "count": 3,
                "sandbox": {
                    "enabled": True,
                    "provider": "srt",
                    "network": "allowlist",
                    "allowed_domains": [],
                },
            },
            "run": {
                "stop": {
                    "max_real_attempts": 3,
                    "max_real_attempts_per_agent": 1,
                }
            },
            "workspace": {
                "results_dir": str(root / "results"),
                "repo_path": str(source),
            },
        }
    )
    config.to_yaml(coral_dir / "config.yaml")
    (coral_dir / "config_dir").write_text(str(root))
    return config


def _prepare_worktree(
    *,
    repo: Path,
    agents_dir: Path,
    coral_dir: Path,
    agent_id: str,
    island: str,
) -> Path:
    worktree = create_agent_worktree(repo, agent_id, agents_dir)
    setup_git_exclude(worktree)
    write_agent_id(worktree, agent_id)
    write_coral_dir(worktree, coral_dir)
    setup_shared_state(worktree, coral_dir, ".opencode", island_id=island)
    return worktree


def _boundary_probe(
    *,
    own_state: Path,
    same_island_worktree: Path,
    foreign_state: Path,
    foreign_worktree: Path,
) -> str:
    """Return Python source executed inside SRT without shell interpolation."""
    return f"""
from pathlib import Path

own_state = Path({str(own_state)!r})
same_island_worktree = Path({str(same_island_worktree)!r})
foreign_state = Path({str(foreign_state)!r})
foreign_worktree = Path({str(foreign_worktree)!r})

assert (own_state / 'notes' / 'marker.txt').read_text() == 'avalon-state\\n'
(own_state / 'notes' / 'inside-srt.txt').write_text('own-write-ok\\n')
assert (same_island_worktree / 'same-island-marker.txt').read_text() == 'avalon-peer\\n'

def require_denied_read(path):
    try:
        path.read_text()
    except OSError:
        return
    raise AssertionError(f'foreign read unexpectedly succeeded: {{path}}')

def require_denied_write(path):
    try:
        path.write_text('isolation-breach\\n')
    except OSError:
        return
    raise AssertionError(f'foreign write unexpectedly succeeded: {{path}}')

require_denied_read(foreign_state / 'notes' / 'marker.txt')
require_denied_write(foreign_state / 'notes' / 'inside-srt.txt')
require_denied_write(same_island_worktree / 'inside-srt.txt')
require_denied_read(foreign_worktree / 'foreign-worktree-marker.txt')
require_denied_write(foreign_worktree / 'inside-srt.txt')
Path('candidate.txt').write_text('submitted from sandbox\\n')
"""


def run_canary(root: Path) -> dict[str, Any]:
    source = root / "source"
    run_dir = root / "run"
    repo = run_dir / "repo"
    agents_dir = run_dir / "agents"
    coral_dir = run_dir / ".coral"

    _init_source_repo(source)
    run_dir.mkdir(parents=True)
    _run(["git", "clone", str(source), str(repo)], cwd=root)
    agents_dir.mkdir()
    _build_state(coral_dir)
    config = _configure(coral_dir, root, source)

    avalon = _prepare_worktree(
        repo=repo,
        agents_dir=agents_dir,
        coral_dir=coral_dir,
        agent_id="agent-avalon",
        island="avalon",
    )
    avalon_mate = _prepare_worktree(
        repo=repo,
        agents_dir=agents_dir,
        coral_dir=coral_dir,
        agent_id="agent-avalon-mate",
        island="avalon",
    )
    atlantis = _prepare_worktree(
        repo=repo,
        agents_dir=agents_dir,
        coral_dir=coral_dir,
        agent_id="agent-atlantis",
        island="atlantis",
    )
    (avalon_mate / "same-island-marker.txt").write_text("avalon-peer\n")
    (atlantis / "foreign-worktree-marker.txt").write_text("atlantis-worktree\n")

    provider = SrtSandbox(config.agents.sandbox)
    provider.validate(config.agents)
    spec = provider.prepare_agent(
        AgentSandboxContext(
            agent_id="agent-avalon",
            worktree_path=avalon,
            coral_dir=coral_dir,
            repo_dir=repo,
            shared_dir_name=".opencode",
            sibling_worktrees=[avalon, avalon_mate],
        )
    )
    sandbox_env = os.environ.copy()
    sandbox_env.update(spec.env)
    own_state = coral_dir / "islands" / "avalon"
    foreign_state = coral_dir / "islands" / "atlantis"

    probe_output = _run(
        [
            *spec.command_prefix,
            sys.executable,
            "-c",
            _boundary_probe(
                own_state=own_state,
                same_island_worktree=avalon_mate,
                foreign_state=foreign_state,
                foreign_worktree=atlantis,
            ),
        ],
        cwd=avalon,
        env=sandbox_env,
    )
    coral_executable = Path(sys.prefix) / "bin" / "coral"
    eval_output = _run(
        [
            *spec.command_prefix,
            str(coral_executable),
            "eval",
            "--no-wait",
            "-m",
            "sandbox isolation canary",
        ],
        cwd=avalon,
        env=sandbox_env,
    )

    own_attempts = sorted((own_state / "attempts").glob("*.json"))
    foreign_attempts = sorted((foreign_state / "attempts").glob("*.json"))
    public_attempts = sorted((coral_dir / "public" / "attempts").glob("*.json"))
    checks = {
        "own_state_read_write": (own_state / "notes" / "inside-srt.txt").read_text()
        == "own-write-ok\n",
        "foreign_state_unchanged": not (foreign_state / "notes" / "inside-srt.txt").exists(),
        "same_island_read_only": not (avalon_mate / "inside-srt.txt").exists(),
        "foreign_worktree_unchanged": not (atlantis / "inside-srt.txt").exists(),
        "attempt_only_in_current_island": len(own_attempts) == 1
        and not foreign_attempts
        and not public_attempts,
        "current_island_budget_lock": (own_state / "real-budget.lock").is_file(),
        "no_root_budget_lock": not (coral_dir / "real-budget.lock").exists(),
        "no_foreign_budget_lock": not (foreign_state / "real-budget.lock").exists(),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise AssertionError("sandbox canary checks failed: " + ", ".join(failures))

    attempt = json.loads(own_attempts[0].read_text())
    return {
        "passed": True,
        "root": str(root),
        "checks": checks,
        "attempt": {
            "commit_hash": attempt.get("commit_hash"),
            "agent_id": attempt.get("agent_id"),
            "status": attempt.get("status"),
            "island_id": (attempt.get("metadata") or {}).get("island_id"),
        },
        "probe_stdout": probe_output,
        "eval_stdout": eval_output,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="new directory for retained canary state (default: /var/tmp timestamped dir)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.output_dir is None:
        root = Path(tempfile.mkdtemp(prefix="coral-multi-island-sandbox-canary-", dir="/var/tmp"))
    else:
        root = args.output_dir.resolve()
        root.mkdir(parents=True, exist_ok=False)
    audit_path = root / "audit.json"
    try:
        audit = run_canary(root)
    except Exception as exc:
        audit_path.write_text(
            json.dumps(
                {"passed": False, "root": str(root), "error": str(exc)},
                indent=2,
            )
            + "\n"
        )
        print(f"FAILED; retained state: {root}", file=sys.stderr)
        raise
    audit_path.write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
