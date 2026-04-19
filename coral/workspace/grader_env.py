"""CORAL-managed grader virtual environment.

Creates and bootstraps `.coral/private/grader_venv/` so that grader code
referenced by `grader.entrypoint` can be imported by a worker subprocess
without polluting CORAL's own venv.

Design:
  - venv lives inside `.coral/private/`, which is already covered by the
    Read deny-rule applied to agent worktrees (worktree.py).
  - We auto-install `coral` from its source root first so that the user's
    grader package can satisfy its `coral` dependency without needing a
    PyPI-released version.
  - User's `grader.setup` shell commands then run with VIRTUAL_ENV pointed
    at the grader venv, so plain `uv pip install ...` lands in the right
    place.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

import coral
from coral.config import GraderConfig
from coral.workspace.repo import _clean_env, run_setup_commands

logger = logging.getLogger(__name__)


def _coral_source_root() -> Path:
    """Return the directory that contains the `coral/` package."""
    return Path(coral.__file__).resolve().parent.parent


def grader_venv_path(coral_dir: Path) -> Path:
    """Path to the grader venv for a given .coral dir."""
    return coral_dir / "private" / "grader_venv"


def grader_python_path(coral_dir: Path) -> Path:
    """Path to the Python interpreter inside the grader venv."""
    return grader_venv_path(coral_dir) / "bin" / "python"


def setup_grader_env(
    coral_dir: Path,
    grader_config: GraderConfig,
    config_dir: Path,
    *,
    rebuild: bool = False,
) -> Path:
    """Create the grader venv and run `grader_config.setup` commands in it.

    Steps:
      1. (Optionally) wipe an existing venv if `rebuild=True`.
      2. Run `uv venv .coral/private/grader_venv/` to create a fresh venv.
      3. Editable-install `coral` from its source root (so user grader
         packages declaring `coral` as a dependency resolve cleanly).
      4. Run each command in `grader_config.setup` with VIRTUAL_ENV /
         PATH pointed at the new venv. `cwd` is `config_dir` so paths
         in setup commands resolve relative to the task directory.

    Returns the path to the venv's Python interpreter.
    Raises RuntimeError on any failure with stdout/stderr in the message.
    """
    venv_dir = grader_venv_path(coral_dir)
    python_path = grader_python_path(coral_dir)

    if rebuild and venv_dir.exists():
        shutil.rmtree(venv_dir)

    venv_dir.parent.mkdir(parents=True, exist_ok=True)

    if not python_path.exists():
        logger.info(f"Creating grader venv at {venv_dir}")
        result = subprocess.run(
            ["uv", "venv", str(venv_dir)],
            capture_output=True,
            text=True,
            env=_clean_env(),
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"`uv venv {venv_dir}` failed (exit {result.returncode}):\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )

    if not python_path.exists():
        raise RuntimeError(
            f"Expected Python interpreter at {python_path} after `uv venv`, but it does not exist"
        )

    extra_env = {
        "VIRTUAL_ENV": str(venv_dir),
        "PATH": f"{venv_dir / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
    }

    coral_install_cmd = f"uv pip install -q -e {_coral_source_root()}"
    run_setup_commands([coral_install_cmd], cwd=config_dir, extra_env=extra_env)

    if grader_config.setup:
        run_setup_commands(grader_config.setup, cwd=config_dir, extra_env=extra_env)

    return python_path
