"""OS-user isolation for agent workspaces (Docker session).

The agent subprocess runs as an unprivileged user (e.g. ``agent``) while the
manager and grader daemon stay root. Standard Unix ownership then enforces the
one boundary that matters: the agent cannot read ``.coral/private/`` (grader
venv, answer keys) — not even via Bash — because it is root-owned mode 700,
while the grader (root) reads it freely.

Ownership model (applied per spawn, idempotent):
  - agent's worktree, the island state root (public/ or islands/<id>/), and the
    run's repo/ are chowned to the agent user — it commits, writes attempts,
    checkpoints shared state.
  - ``.coral/private/`` is forced back to root:root mode 700.
  - root can read/write everything regardless, so the grader is unaffected.

Requires CORAL to run as root (true inside the Docker session). When
``agents.isolate_user`` is set but CORAL is not root, this raises rather than
silently running the agent with full privileges.
"""

from __future__ import annotations

import logging
import os
import pwd
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserSpec:
    name: str
    uid: int
    gid: int
    home: str


class UserIsolationError(RuntimeError):
    """Raised when isolate_user is requested but cannot be honored."""


def is_enabled(isolate_user: str | None) -> bool:
    return bool(isolate_user)


def resolve(username: str) -> UserSpec:
    """Look up the target user, validating prerequisites.

    Raises UserIsolationError if CORAL is not root (can't drop privileges) or
    the user does not exist (the Docker image must provide it).
    """
    if os.geteuid() != 0:
        raise UserIsolationError(
            f"agents.isolate_user={username!r} requires CORAL to run as root so it "
            "can chown the workspace and drop the agent to that user. This is the "
            "Docker session's model; on the host, run without isolate_user."
        )
    try:
        pw = pwd.getpwnam(username)
    except KeyError as e:
        raise UserIsolationError(
            f"isolate_user={username!r}: no such user. The Docker image must create it."
        ) from e
    return UserSpec(name=username, uid=pw.pw_uid, gid=pw.pw_gid, home=pw.pw_dir)


def _chown_tree(path: Path, spec: UserSpec) -> None:
    if not path.exists():
        return
    subprocess.run(
        ["chown", "-R", f"{spec.uid}:{spec.gid}", str(path)],
        capture_output=True,
        check=False,
    )


def _lock_private(private_dir: Path) -> None:
    """Force the private dir root-owned and unreadable to non-root."""
    if not private_dir.exists():
        return
    subprocess.run(["chown", "-R", "0:0", str(private_dir)], capture_output=True, check=False)
    # 700 on the top dir is the gate; the agent can't traverse into it at all.
    os.chmod(private_dir, 0o700)


def apply_ownership(
    worktree_path: Path,
    coral_dir: Path,
    repo_dir: Path,
    spec: UserSpec,
    *,
    island_id: str | int | None = None,
) -> None:
    """Chown agent-facing paths to ``spec`` and lock ``.coral/private/`` to root.

    Idempotent and safe to call per spawn. Shared paths (state root, repo) are
    re-chowned to the same user each time, which is harmless.
    """
    from coral.hub._island import island_root

    state_root = island_root(coral_dir, island_id)

    # Agent-owned: its worktree, the shared state it reads/writes, the repo it
    # commits to. The grader is root, so root-vs-agent ownership of repo/ is
    # fine — root bypasses permission bits.
    _chown_tree(worktree_path, spec)
    _chown_tree(state_root, spec)
    _chown_tree(repo_dir, spec)

    # The one hard boundary.
    _lock_private(coral_dir / "private")

    # Mixed ownership (root grader operating an agent-owned repo, and vice
    # versa) trips git's dubious-ownership guard. Trust all repos system-wide;
    # these are throwaway per-run repos, not a security surface.
    subprocess.run(
        ["git", "config", "--system", "--add", "safe.directory", "*"],
        capture_output=True,
        check=False,
    )


def provision_home_state(spec: UserSpec, shared_dir_name: str) -> str:
    """Give the agent user a writable home copy of the runtime's creds/state.

    The Docker entrypoint stages credentials into root's home
    (``/root/.codex``, ``/root/.claude``, ...). The agent runs with
    ``HOME=<spec.home>`` and looks there instead, so mirror the runtime's state
    dir into the agent's home and chown it. Returns the agent HOME to set in the
    subprocess env.
    """
    home = Path(spec.home)
    home.mkdir(parents=True, exist_ok=True)
    src = Path("/root") / shared_dir_name
    dst = home / shared_dir_name
    if src.is_dir() and not dst.exists():
        subprocess.run(["cp", "-a", str(src), str(dst)], capture_output=True, check=False)
    _chown_tree(home, spec)
    return str(home)
