"""Platform venv path helpers (#228)."""

from pathlib import Path

from coral.venv_paths import (
    venv_bin_dir,
    venv_bin_dir_name,
    venv_python,
    venv_python_name,
)


def test_posix_layout():
    assert venv_bin_dir_name(windows=False) == "bin"
    assert venv_python_name(windows=False) == "python"
    root = Path("/tmp/proj/.venv")
    assert venv_bin_dir(root, windows=False) == root / "bin"
    assert venv_python(root, windows=False) == root / "bin" / "python"


def test_windows_layout():
    assert venv_bin_dir_name(windows=True) == "Scripts"
    assert venv_python_name(windows=True) == "python.exe"
    root = Path(r"C:\proj\.venv")
    assert venv_bin_dir(root, windows=True) == root / "Scripts"
    assert venv_python(root, windows=True) == root / "Scripts" / "python.exe"
