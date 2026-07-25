"""Preflight and trace audits for multi-island information isolation.

The experiment estimand is undefined if a no-migration island can inspect a
foreign worktree, branch, note, or attempt. These checks complement CORAL's
sandbox tests with fail-closed launch and post-run gates used by the research
matrices.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

_RAW_GIT = re.compile(r"\bgit(?:\s|$)")
_ISLAND_PATH = re.compile(r"[\\/]\.coral[\\/]islands[\\/]([^\\/\s\"']+)")
_AGENT_PATH = re.compile(r"[\\/]agents[\\/]([^\\/\s\"']+)")


def sandbox_contract_errors() -> list[str]:
    """Return launch-blocking errors in the active sandbox implementation."""
    from coral.config import SandboxConfig
    from coral.sandbox.srt import build_srt_settings
    from coral.workspace.worktree import setup_opencode_settings

    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="coral-isolation-preflight-") as raw:
        root = Path(raw)
        coral_dir = root / ".coral"
        own_state = coral_dir / "islands" / "avalon"
        foreign_state = coral_dir / "islands" / "atlantis"
        private = coral_dir / "private"
        public = coral_dir / "public"
        repo_git = root / "repo" / ".git"
        worktree = root / "agents" / "agent-avalon"
        foreign_worktree = root / "agents" / "agent-atlantis"
        for path in (
            own_state,
            foreign_state,
            private,
            public,
            repo_git,
            worktree,
            foreign_worktree,
        ):
            path.mkdir(parents=True, exist_ok=True)
        (worktree / ".coral_island").write_text("avalon\n")

        settings = build_srt_settings(
            SandboxConfig(enabled=True, network="allowlist"),
            worktree_path=worktree,
            coral_dir=coral_dir,
            repo_dir=root / "repo",
            shared_dir_name=".opencode",
            proxy_port=None,
            sibling_worktrees=[worktree],
        )
        fs = settings["filesystem"]
        allow_read = set(fs["allowRead"])
        allow_write = set(fs["allowWrite"])
        deny_read = set(fs["denyRead"])
        deny_write = set(fs["denyWrite"])
        islands = str((coral_dir / "islands").resolve())
        agents = str((root / "agents").resolve())
        if islands in allow_read:
            errors.append("srt broadly allows reading the common islands root")
        if str(coral_dir.resolve()) in allow_write or islands in allow_write:
            errors.append("srt broadly allows writing common CORAL/island state")
        own = str(own_state.resolve())
        if own not in allow_read or own not in allow_write:
            errors.append("srt does not grant the current island state root")
        foreign = str(foreign_state.resolve())
        if foreign in allow_read or foreign in allow_write:
            errors.append("srt explicitly grants a foreign island state root")
        if agents not in deny_read or agents not in deny_write:
            errors.append("srt does not deny the common worktree parent")
        foreign_agent = str(foreign_worktree.resolve())
        if foreign_agent in allow_read or foreign_agent in allow_write:
            errors.append("srt explicitly grants a foreign-island worktree")

        setup_opencode_settings(worktree, coral_dir, island_id="avalon")
        opencode = json.loads((worktree / ".opencode" / "opencode.json").read_text())
        bash = opencode.get("permission", {}).get("bash", {})
        if bash.get("git *") != "deny" or bash.get("* git *") != "deny":
            errors.append("OpenCode multi-island policy does not deny raw Git inspection")
    return errors


def require_sandbox_contract() -> None:
    errors = sandbox_contract_errors()
    if errors:
        raise RuntimeError("multi-island isolation preflight failed: " + "; ".join(errors))


def _tool_input(line: str) -> tuple[str, str] | None:
    try:
        event = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(event, dict) or event.get("type") != "tool_use":
        return None
    part = event.get("part")
    if not isinstance(part, dict):
        return None
    tool = str(part.get("tool", ""))
    state = part.get("state")
    if not isinstance(state, dict):
        return None
    payload = state.get("input")
    if not isinstance(payload, (dict, list, str)):
        return None
    rendered = payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True)
    return tool, rendered


def trace_isolation_violations(run_dir: Path) -> list[str]:
    """Find explicit cross-island paths or raw Git inspection in runtime logs."""
    islands_root = run_dir / ".coral" / "islands"
    if not islands_root.is_dir():
        return []
    agents_dir = run_dir / "agents"
    agent_islands: dict[str, str] = {}
    for worktree in agents_dir.iterdir() if agents_dir.is_dir() else ():
        try:
            island = (worktree / ".coral_island").read_text().strip()
        except OSError:
            continue
        if island:
            agent_islands[worktree.name] = island

    violations: list[str] = []
    for island_dir in sorted(path for path in islands_root.iterdir() if path.is_dir()):
        log_dir = island_dir / "logs"
        if not log_dir.is_dir():
            continue
        for log in sorted(log_dir.glob("*.log")):
            try:
                lines = log.read_text(errors="replace").splitlines()
            except OSError:
                continue
            for line_no, line in enumerate(lines, start=1):
                parsed = _tool_input(line)
                if parsed is None:
                    continue
                tool, payload = parsed
                if tool == "bash" and _RAW_GIT.search(payload):
                    violations.append(f"{log.name}:{line_no}:raw-git-inspection")
                for match in _ISLAND_PATH.finditer(payload):
                    foreign = match.group(1)
                    if foreign != island_dir.name:
                        violations.append(
                            f"{log.name}:{line_no}:foreign-island-path:{foreign}"
                        )
                for match in _AGENT_PATH.finditer(payload):
                    agent = match.group(1)
                    if agent_islands.get(agent) not in {None, island_dir.name}:
                        violations.append(
                            f"{log.name}:{line_no}:foreign-agent-path:{agent}"
                        )
    return sorted(set(violations))


def isolation_gate(run_dir: Path) -> tuple[bool, list[str]]:
    violations = trace_isolation_violations(run_dir)
    return not violations, violations
