"""Helpers for resolving agent CLI binaries consistently."""

from __future__ import annotations

import shutil
from pathlib import Path


def resolve_runtime_cli(runtime: str, command: str) -> str | None:
    """Resolve a runtime CLI command to an executable path.

    On WSL, ``codex`` on PATH can be the Windows npm shim under ``/mnt/c``.
    CORAL's local/tmux private-safe mode needs the Linux Codex binary so bwrap
    can project it into the agent namespace. Prefer ``~/.local/bin/codex`` for
    the default Codex command and treat a Windows shim alone as missing.
    """

    resolved = _resolve_command(command)
    if runtime == "codex" and command == "codex":
        native = Path.home() / ".local" / "bin" / "codex"
        if native.exists():
            return str(native)
        if resolved and _is_windows_mount_path(Path(resolved)):
            return None
    return resolved


def _resolve_command(command: str) -> str | None:
    candidate = Path(command).expanduser()
    if candidate.is_absolute() or "/" in command:
        return str(candidate) if candidate.exists() else None
    return shutil.which(command)


def _is_windows_mount_path(path: Path) -> bool:
    return len(path.parts) >= 3 and path.parts[0] == "/" and path.parts[1] == "mnt"
