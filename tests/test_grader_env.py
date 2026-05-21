"""Tests for coral.workspace.grader_env."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from coral.config import GraderConfig
from coral.workspace.grader_env import (
    grader_python_path,
    grader_venv_path,
    setup_grader_env,
)


def _uv_available() -> bool:
    try:
        subprocess.run(["uv", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


pytestmark = pytest.mark.skipif(not _uv_available(), reason="uv binary required")


def test_setup_grader_env_creates_venv(tmp_path: Path) -> None:
    coral_dir = tmp_path / ".coral"
    coral_dir.mkdir()
    config_dir = tmp_path / "task"
    config_dir.mkdir()

    grader_config = GraderConfig(
        entrypoint="ignored.for.this.test:Grader",
        setup=[],
    )

    python_path = setup_grader_env(coral_dir, grader_config, config_dir)

    assert python_path == grader_python_path(coral_dir)
    assert python_path.exists()
    assert grader_venv_path(coral_dir).is_dir()


def test_setup_grader_env_installs_coral_so_worker_can_import(tmp_path: Path) -> None:
    coral_dir = tmp_path / ".coral"
    coral_dir.mkdir()
    config_dir = tmp_path / "task"
    config_dir.mkdir()

    grader_config = GraderConfig(setup=[])
    python_path = setup_grader_env(coral_dir, grader_config, config_dir)

    # The worker subprocess must be able to `from coral.grader import TaskGrader`
    result = subprocess.run(
        [str(python_path), "-c", "from coral.grader import TaskGrader; print('ok')"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "ok" in result.stdout


def test_setup_grader_env_runs_user_setup_in_the_venv(tmp_path: Path) -> None:
    """User-supplied setup commands should land in the grader venv (not CORAL's)."""
    coral_dir = tmp_path / ".coral"
    coral_dir.mkdir()
    config_dir = tmp_path / "task"
    config_dir.mkdir()

    # Install a tiny pure-Python package that we can later import-check.
    grader_config = GraderConfig(
        setup=["uv pip install --quiet wheel"],
    )

    python_path = setup_grader_env(coral_dir, grader_config, config_dir)

    result = subprocess.run(
        [str(python_path), "-c", "import wheel; print(wheel.__name__)"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "wheel" in result.stdout


def test_setup_grader_env_is_idempotent(tmp_path: Path) -> None:
    """Calling setup_grader_env twice does not recreate the venv."""
    coral_dir = tmp_path / ".coral"
    coral_dir.mkdir()
    config_dir = tmp_path / "task"
    config_dir.mkdir()

    grader_config = GraderConfig(setup=[])

    setup_grader_env(coral_dir, grader_config, config_dir)
    venv_dir = grader_venv_path(coral_dir)
    marker = venv_dir / ".sentinel"
    marker.write_text("first run")

    setup_grader_env(coral_dir, grader_config, config_dir)
    assert marker.exists() and marker.read_text() == "first run"


def test_setup_grader_env_rebuild_recreates_venv(tmp_path: Path) -> None:
    coral_dir = tmp_path / ".coral"
    coral_dir.mkdir()
    config_dir = tmp_path / "task"
    config_dir.mkdir()

    grader_config = GraderConfig(setup=[])

    setup_grader_env(coral_dir, grader_config, config_dir)
    venv_dir = grader_venv_path(coral_dir)
    marker = venv_dir / ".sentinel"
    marker.write_text("first run")

    setup_grader_env(coral_dir, grader_config, config_dir, rebuild=True)
    assert not marker.exists()


def test_coral_install_command_editable() -> None:
    """direct_url.json with `dir_info.editable` -> `uv pip install -e <path>`."""
    from coral.workspace.grader_env import _coral_install_command

    origin = {
        "url": "file:///Users/dev/CORAL",
        "dir_info": {"editable": True},
    }
    assert _coral_install_command(origin) == "uv pip install -q -e /Users/dev/CORAL"


def test_coral_install_command_git_vcs() -> None:
    """direct_url.json with `vcs_info` -> `uv pip install git+<url>@<commit>`."""
    from coral.workspace.grader_env import _coral_install_command

    origin = {
        "url": "https://github.com/Human-Agent-Society/CORAL.git",
        "vcs_info": {"vcs": "git", "commit_id": "55a9ad024abc", "requested_revision": "main"},
    }
    expected = "uv pip install -q git+https://github.com/Human-Agent-Society/CORAL.git@55a9ad024abc"
    assert _coral_install_command(origin) == expected


def test_coral_install_command_fork_url_is_preserved() -> None:
    """If user installed from a fork, the grader venv gets coral from that fork too."""
    from coral.workspace.grader_env import _coral_install_command

    origin = {
        "url": "https://github.com/my-org/coral-fork.git",
        "vcs_info": {"vcs": "git", "commit_id": "deadbeef"},
    }
    cmd = _coral_install_command(origin)
    assert "my-org/coral-fork.git" in cmd
    assert "@deadbeef" in cmd


def test_coral_install_command_rejects_archive_install() -> None:
    """Archive (tarball) installs aren't supported — clear error."""
    from coral.workspace.grader_env import _coral_install_command

    origin = {
        "url": "file:///tmp/coral.tar.gz",
        "archive_info": {"hash": "sha256=abc"},
    }
    with pytest.raises(RuntimeError, match="Unsupported coral install origin"):
        _coral_install_command(origin)


def test_coral_install_command_rejects_non_git_vcs() -> None:
    from coral.workspace.grader_env import _coral_install_command

    origin = {
        "url": "hg+https://example.com/coral",
        "vcs_info": {"vcs": "hg", "commit_id": "abc"},
    }
    with pytest.raises(RuntimeError, match="Only git VCS"):
        _coral_install_command(origin)


def test_coral_install_origin_raises_when_direct_url_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the installer didn't write PEP 610 metadata, we error clearly."""
    import sysconfig

    from coral.workspace import grader_env

    # Build a fake purelib that has a dist-info but no direct_url.json.
    fake_purelib = tmp_path / "site-packages"
    fake_purelib.mkdir()
    (fake_purelib / "coral-9.9.9.dist-info").mkdir()

    monkeypatch.setattr(sysconfig, "get_paths", lambda: {"purelib": str(fake_purelib)})

    with pytest.raises(RuntimeError, match="direct_url.json"):
        grader_env._coral_install_origin()


def test_setup_grader_env_replicates_a_simulated_git_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test for #114.

    Simulates a `uv tool install git+...` install (non-editable, VCS origin)
    by monkeypatching `_coral_install_origin` to return a VCS-shaped dict
    pointing at the local dev repo. The grader venv should then `uv pip
    install` from that source — exercising the real code path that breaks
    today's README install.
    """
    from coral.workspace import grader_env

    repo_root = Path(__file__).resolve().parent.parent
    head_sha = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    fake_origin = {
        "url": f"file://{repo_root}",
        "vcs_info": {"vcs": "git", "commit_id": head_sha},
    }
    monkeypatch.setattr(grader_env, "_coral_install_origin", lambda: fake_origin)

    coral_dir = tmp_path / ".coral"
    coral_dir.mkdir()
    config_dir = tmp_path / "task"
    config_dir.mkdir()

    grader_config = GraderConfig(setup=[])
    python_path = setup_grader_env(coral_dir, grader_config, config_dir)

    # Worker subprocess must still be able to import coral.
    result = subprocess.run(
        [str(python_path), "-c", "from coral.grader import TaskGrader; print('ok')"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "ok" in result.stdout


def test_setup_grader_env_raises_on_failed_setup_command(tmp_path: Path) -> None:
    coral_dir = tmp_path / ".coral"
    coral_dir.mkdir()
    config_dir = tmp_path / "task"
    config_dir.mkdir()

    grader_config = GraderConfig(
        setup=["false"],  # always fails
    )
    with pytest.raises(RuntimeError, match="false"):
        setup_grader_env(coral_dir, grader_config, config_dir)
