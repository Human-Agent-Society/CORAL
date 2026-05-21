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


@pytest.mark.parametrize(
    "version, expected_ref",
    [
        # Tagged release → vX.Y.Z
        ("0.5.2", "v0.5.2"),
        ("1.0.0", "v1.0.0"),
        ("1.0.0rc1", "v1.0.0rc1"),
        # Dev install → sha from hatch-vcs local-version segment
        ("0.5.2.dev24+g55a9ad024.d20260520", "55a9ad024"),
        ("0.5.2.dev24+g55a9ad024", "55a9ad024"),
        ("0.5.2.dev24+g55a9ad024.dirty", "55a9ad024"),
        (
            "0.6.0.dev1+gabcdef0123456789abcdef0123456789abcdef01",
            "abcdef0123456789abcdef0123456789abcdef01",
        ),
    ],
)
def test_coral_git_ref_derivation(
    version: str, expected_ref: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_coral_git_ref()` pins to the running coral version via the sha or tag."""
    import coral
    from coral.workspace.grader_env import _coral_git_ref

    monkeypatch.setattr(coral, "__version__", version)
    assert _coral_git_ref() == expected_ref


def test_setup_grader_env_works_without_editable_source_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test for #114.

    When CORAL is installed via `uv tool install`, `Path(coral.__file__).parent.parent`
    is a `site-packages/` dir (no `pyproject.toml`), so editable-installing it fails.
    `_coral_source_root()` returns None in that case and the venv falls back to
    installing CORAL from git at the running commit. We point the install at a
    local `file://` URL (the dev checkout) so the test stays offline.
    """
    from coral.workspace import grader_env

    repo_root = Path(__file__).resolve().parent.parent
    head_sha = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    monkeypatch.setattr(grader_env, "_coral_source_root", lambda: None)
    monkeypatch.setattr(grader_env, "CORAL_GIT_URL", f"file://{repo_root}")
    monkeypatch.setattr(grader_env, "_coral_git_ref", lambda: head_sha)

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
