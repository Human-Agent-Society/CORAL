"""Grader loader: resolves ``config.grader.entrypoint`` to a SubprocessGrader.

The entrypoint (``module.path:ClassName``) is imported inside
``.coral/private/grader_venv/`` (set up by ``coral.workspace.grader_env``) by
a worker subprocess — see :class:`SubprocessGrader`.

Legacy paths have been removed: ``grader.type`` / ``grader.module`` get a
clear error from :func:`coral.config._preprocess`, and the old
``eval/grader.py`` in-process auto-discovery is no longer supported — package
the grader and point ``grader.entrypoint`` at it.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from coral.config import CoralConfig
from coral.grader.subprocess_grader import SubprocessGrader
from coral.workspace.grader_env import grader_python_path

logger = logging.getLogger(__name__)


def load_grader(config: CoralConfig, coral_dir: str | Path) -> Any:
    """Resolve the grader for a task.

    Returns a grader implementing the GraderInterface protocol. Setting
    ``private_dir`` on the returned object is part of this function's contract
    so callers don't have to.
    """
    coral_dir = Path(coral_dir)
    private_dir = coral_dir / "private"

    if not config.grader.entrypoint:
        raise ValueError(
            "No grader configured. Set grader.entrypoint = "
            "'your_pkg.module:Grader' in task.yaml and grader.setup to "
            'install the package (e.g. "uv pip install -e ./grader"). '
            "The legacy eval/grader.py auto-discovery has been removed — "
            "see docs/guides/custom-grader."
        )

    worker_python = grader_python_path(coral_dir)
    if not worker_python.exists():
        raise RuntimeError(
            f"Grader venv not initialized at {worker_python.parent}. "
            f"Run `coral validate` or `coral start` first so that "
            f"`coral.workspace.grader_env.setup_grader_env` can create it."
        )
    logger.info(
        f"Loading grader entrypoint {config.grader.entrypoint!r} via worker {worker_python}"
    )
    return SubprocessGrader(
        entrypoint=config.grader.entrypoint,
        worker_python=worker_python,
        config=config.grader,
        private_dir=str(private_dir),
    )
