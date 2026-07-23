"""Tests for the chat workspace path gate + task scaffolding (coral/chat/workspace.py).

The gate is the security boundary for pointing an agent at an arbitrary
user directory, so the blacklist + symlink-escape cases are covered
explicitly (ported from multica's local_directory validation).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from coral.chat.workspace import (
    LocalPathError,
    browse_directory,
    scaffold_task,
    validate_local_path,
)


def test_accepts_normal_directory(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    assert validate_local_path(proj) == Path(os.path.normpath(str(proj)))


def test_rejects_empty_and_relative() -> None:
    with pytest.raises(LocalPathError):
        validate_local_path("")
    with pytest.raises(LocalPathError):
        validate_local_path(None)
    with pytest.raises(LocalPathError):
        validate_local_path("relative/path")


def test_rejects_filesystem_root() -> None:
    with pytest.raises(LocalPathError):
        validate_local_path("/")


@pytest.mark.parametrize("banned", ["/etc", "/tmp", "/usr", "/var"])
def test_rejects_protected_system_roots(banned: str) -> None:
    with pytest.raises(LocalPathError):
        validate_local_path(banned)


def test_rejects_home_directory() -> None:
    with pytest.raises(LocalPathError):
        validate_local_path(str(Path.home()))


def test_rejects_nonexistent(tmp_path: Path) -> None:
    with pytest.raises(LocalPathError):
        validate_local_path(tmp_path / "does-not-exist")


def test_rejects_file_not_dir(tmp_path: Path) -> None:
    f = tmp_path / "a-file"
    f.write_text("x")
    with pytest.raises(LocalPathError):
        validate_local_path(f)


def test_rejects_symlink_escaping_to_protected(tmp_path: Path) -> None:
    # A symlink whose target is a protected location must be rejected by the
    # post-resolution check, even though the link path itself looks innocent.
    link = tmp_path / "escape"
    link.symlink_to("/etc")
    with pytest.raises(LocalPathError):
        validate_local_path(link)


def test_rejects_symlink_escaping_to_home(tmp_path: Path) -> None:
    link = tmp_path / "home-link"
    link.symlink_to(Path.home())
    with pytest.raises(LocalPathError):
        validate_local_path(link)


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "getuid") and os.getuid() == 0),
    reason="permission bits not enforced for root / on Windows",
)
def test_rejects_unwritable_directory(tmp_path: Path) -> None:
    ro = tmp_path / "readonly"
    ro.mkdir()
    ro.chmod(0o500)  # r-x, no write
    try:
        with pytest.raises(LocalPathError):
            validate_local_path(ro)
    finally:
        ro.chmod(0o700)  # restore so tmp cleanup can remove it


def test_scaffold_task_creates_task(tmp_path: Path) -> None:
    dest = scaffold_task(tmp_path, "my-task")
    assert dest == tmp_path / "my-task"
    assert (dest / "task.yaml").exists()
    assert (dest / "seed").is_dir()
    assert (dest / "grader").is_dir()


def test_scaffold_task_rejects_bad_name(tmp_path: Path) -> None:
    with pytest.raises(LocalPathError):
        scaffold_task(tmp_path, "../escape")
    with pytest.raises(LocalPathError):
        scaffold_task(tmp_path, "")


def test_browse_directory_lists_subdirs(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / ".hidden").mkdir()  # omitted
    (tmp_path / "a-file").write_text("x")  # files omitted

    result = browse_directory(tmp_path)
    names = [e["name"] for e in result["entries"]]
    assert names == ["alpha", "beta"]  # sorted, no hidden, no files
    assert result["path"] == str(tmp_path.resolve())
    assert result["parent"] == str(tmp_path.resolve().parent)
    assert all(e["path"].startswith(str(tmp_path.resolve())) for e in result["entries"])


def test_browse_directory_defaults_to_home_and_rejects_nonexistent(tmp_path: Path) -> None:
    home = browse_directory(None)
    assert home["path"] == str(Path.home().resolve())
    with pytest.raises(LocalPathError):
        browse_directory(tmp_path / "nope")
