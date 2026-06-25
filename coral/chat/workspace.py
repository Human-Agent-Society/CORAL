"""Workspace selection + path gating for chat sessions (P2).

The chat agent runs in a working directory the user picks. Because that
directory is arbitrary and the agent can write inside it, the path is run
through :func:`validate_local_path` — a port of multica's
``local_directory.go::validateLocalPath``:

  - absolute,
  - not a protected system root or ``$HOME`` (checked both literally AND
    after symlink resolution, so ``~/proj/link -> $HOME`` and macOS's
    ``/private/tmp`` aliasing of ``/tmp`` can't slip through),
  - exists and is a directory,
  - readable + writable (a real probe file is created and removed).

New task workspaces are scaffolded via ``coral init``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class LocalPathError(ValueError):
    """A user-supplied workspace path failed validation.

    The message is safe to surface verbatim to the UI.
    """


def _system_roots() -> list[str]:
    if os.name == "nt":
        return [
            r"C:\Users",
            r"C:\ProgramData",
            r"C:\Program Files",
            r"C:\Program Files (x86)",
            r"C:\Windows",
        ]
    return [
        "/",
        "/Users",
        "/Users/Shared",
        "/home",
        "/root",
        "/var",
        "/etc",
        "/tmp",
        "/usr",
        "/opt",
    ]


def _protected_targets() -> list[Path]:
    targets = [Path(r) for r in _system_roots()]
    try:
        targets.append(Path.home())
    except (RuntimeError, OSError):  # pragma: no cover - home undefined
        pass
    return targets


def _is_fs_root(p: Path) -> bool:
    return p == p.parent


def _reject_if_protected(p: Path, *, resolved: bool) -> None:
    """Raise if ``p`` is a filesystem root, a protected system dir, or $HOME.

    When ``resolved`` is True, each protected target is *also* compared in its
    symlink-resolved form, so a path that canonicalizes onto a banned target
    (e.g. ``/private/etc`` for ``/etc`` on macOS) is rejected too.
    """
    cleaned = Path(os.path.normpath(str(p)))
    if _is_fs_root(cleaned):
        raise LocalPathError(f"refusing a filesystem root: {cleaned}")
    for banned in _protected_targets():
        banned_clean = Path(os.path.normpath(str(banned)))
        if cleaned == banned_clean:
            raise LocalPathError(f"refusing a protected location: {cleaned}")
        if resolved:
            try:
                if cleaned == Path(os.path.realpath(banned_clean)):
                    raise LocalPathError(
                        f"refusing a protected location (resolves to {banned_clean}): {cleaned}"
                    )
            except OSError:  # pragma: no cover - realpath rarely raises
                pass


def _probe_read_write(d: Path) -> None:
    try:
        os.listdir(d)
    except OSError as e:
        raise LocalPathError(f"cannot read directory {d}: {e}") from e
    try:
        fd, tmp = tempfile.mkstemp(prefix=".coral-chat-rwcheck-", dir=str(d))
        os.close(fd)
        os.unlink(tmp)
    except OSError as e:
        raise LocalPathError(f"directory is not writable {d}: {e}") from e


def validate_local_path(raw: str | os.PathLike[str] | None) -> Path:
    """Validate a user-supplied workspace path; return the cleaned abs Path.

    Raises :class:`LocalPathError` on any failure.
    """
    if raw is None or str(raw).strip() == "":
        raise LocalPathError("workspace path is empty")
    p = Path(str(raw).strip()).expanduser()
    if not p.is_absolute():
        raise LocalPathError(f"workspace path must be absolute: {raw!r}")
    cleaned = Path(os.path.normpath(str(p)))

    # Cheap literal check first.
    _reject_if_protected(cleaned, resolved=False)

    if not cleaned.exists():
        raise LocalPathError(f"workspace path does not exist: {cleaned}")
    if not cleaned.is_dir():
        raise LocalPathError(f"workspace path is not a directory: {cleaned}")

    # Re-check after resolving symlinks (the security-critical step).
    real = Path(os.path.realpath(cleaned))
    _reject_if_protected(real, resolved=True)

    _probe_read_write(cleaned)
    return cleaned


def _coral_bin() -> str:
    # Prefer the `coral` next to the running interpreter (same install),
    # then fall back to PATH.
    candidate = Path(sys.executable).parent / "coral"
    if candidate.exists():
        return str(candidate)
    found = shutil.which("coral")
    if found:
        return found
    raise LocalPathError("the `coral` CLI is not on PATH")


def scaffold_task(parent: str | os.PathLike[str], name: str) -> Path:
    """Scaffold a new CORAL task under ``parent/name`` via ``coral init``.

    ``parent`` is validated with :func:`validate_local_path`; ``name`` must be
    a single path segment. Returns the new task directory.
    """
    if not name or not name.strip():
        raise LocalPathError("task name is empty")
    name = name.strip()
    if "/" in name or "\\" in name or name in (".", ".."):
        raise LocalPathError(f"invalid task name: {name!r}")

    parent_dir = validate_local_path(parent)
    dest = parent_dir / name
    if dest.exists() and any(dest.iterdir()):
        raise LocalPathError(f"task directory already exists and is not empty: {dest}")

    proc = subprocess.run(
        [_coral_bin(), "init", str(dest)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise LocalPathError(f"`coral init` failed: {detail}")
    return dest
