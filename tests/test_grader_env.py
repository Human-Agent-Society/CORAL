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
