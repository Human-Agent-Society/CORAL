"""CORAL-managed grader virtual environment.

Creates and bootstraps `.coral/private/grader_venv/` so that grader code
referenced by `grader.entrypoint` can be imported by a worker subprocess
without polluting CORAL's own venv.

Design:
  - venv lives inside `.coral/private/`, which is already covered by the
    Read deny-rule applied to agent worktrees (worktree.py).
  - The grader venv must be able to `import coral` so user grader packages
    can declare `coral` as a dependency. We use one of two strategies:
      * Editable-install path (dev / source checkout): we detect a
        `pyproject.toml` next to the `coral/` package and run
        `uv pip install -e <source_root>` into the new venv.
      * Git-install path (installed package, e.g. `uv tool install`): no
        source tree is available, so we install CORAL from git at the same
        commit the host is running. The sha lives in `coral.__version__`
        thanks to hatch-vcs's local-version segment.
  - User's `grader.setup` shell commands then run with VIRTUAL_ENV pointed
    at the grader venv, so plain `uv pip install ...` lands in the right
    place.

Fork or mirror users should clone their fork locally and run `uv sync` —
that gives an editable install which we detect via `_coral_source_root` and
prefer over the canonical git URL.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import coral
from coral.config import GraderConfig
from coral.workspace.repo import _clean_env, run_setup_commands

logger = logging.getLogger(__name__)


CORAL_GIT_URL = "https://github.com/Human-Agent-Society/CORAL.git"


def _coral_source_root() -> Path | None:
    """Return the source checkout that contains the `coral/` package, or None.

    Returns the directory above `coral/__init__.py` only when it looks like a
    real Python project (i.e. contains a `pyproject.toml`). When CORAL is
    installed as a regular package — for example via `uv tool install`, which
    the README's `install.sh` uses — that grandparent path is a
    `site-packages/` directory and there's no source tree to editable-install.
    In that case we return None and the caller installs CORAL from git instead.
    """
    candidate = Path(coral.__file__).resolve().parent.parent
    if (candidate / "pyproject.toml").exists():
        return candidate
    return None


def _coral_git_ref() -> str:
    """Return a git ref pinning to the running CORAL version.

    `hatch-vcs` writes the commit sha into the local-version segment of dev
    versions (e.g. ``0.5.2.dev24+g55a9ad024.d20260520``) and produces a clean
    ``X.Y.Z`` string for tagged releases. We extract the sha when present and
    fall back to ``vX.Y.Z`` so a tagged release installs by tag.

    Returns a string suitable for ``uv pip install git+<url>@<ref>``.
    """
    version = coral.__version__
    sha_match = re.search(r"\+g([0-9a-f]{7,40})", version)
    if sha_match:
        return sha_match.group(1)
    return f"v{version}"


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
      2. Run `uv venv .coral/private/grader_venv/` to create a fresh venv
         against `sys.executable` so the venv matches CORAL's interpreter.
      3. Install `coral` into the venv: editable from a local source tree
         when one exists, or `git+<url>@<sha>` matching the running version
         when CORAL was installed as a regular package.
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
        venv_cmd = ["uv", "venv", "--python", sys.executable, str(venv_dir)]
        result = subprocess.run(
            venv_cmd,
            capture_output=True,
            text=True,
            env=_clean_env(),
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"`{' '.join(venv_cmd)}` failed (exit {result.returncode}):\n"
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

    source_root = _coral_source_root()
    if source_root is not None:
        coral_install_cmd = f"uv pip install -q -e {source_root}"
    else:
        coral_install_cmd = f"uv pip install -q git+{CORAL_GIT_URL}@{_coral_git_ref()}"
    run_setup_commands([coral_install_cmd], cwd=config_dir, extra_env=extra_env)

    if grader_config.setup:
        run_setup_commands(grader_config.setup, cwd=config_dir, extra_env=extra_env)

    return python_path
