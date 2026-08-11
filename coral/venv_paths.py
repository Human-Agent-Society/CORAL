"""Platform-aware virtualenv path helpers (POSIX bin/ vs Windows Scripts/)."""

from __future__ import annotations

import sys
from pathlib import Path


def venv_bin_dir_name(*, windows: bool | None = None) -> str:
    """Directory under a venv root that holds executables."""
    if windows is None:
        windows = sys.platform == "win32"
    return "Scripts" if windows else "bin"


def venv_python_name(*, windows: bool | None = None) -> str:
    """Interpreter filename inside the venv bin directory."""
    if windows is None:
        windows = sys.platform == "win32"
    return "python.exe" if windows else "python"


def venv_bin_dir(venv_root: Path | str, *, windows: bool | None = None) -> Path:
    return Path(venv_root) / venv_bin_dir_name(windows=windows)


def venv_python(venv_root: Path | str, *, windows: bool | None = None) -> Path:
    return venv_bin_dir(venv_root, windows=windows) / venv_python_name(windows=windows)
