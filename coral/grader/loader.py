"""Grader loader: entrypoint-first with eval/grader.py as a deprecated fallback.

Resolution order:

1. ``config.grader.entrypoint`` → :class:`SubprocessGrader` running inside
   ``.coral/private/grader_venv/`` (set up by ``coral.workspace.grader_env``).
2. ``.coral/private/eval/grader.py`` exists → in-process load with a
   ``DeprecationWarning`` pointing to the entrypoint migration.
3. Otherwise → :class:`ValueError` with a migration hint.

Legacy ``grader.type`` and ``grader.module`` fields have been removed; tasks
that still set them get a clear error from :func:`coral.config._preprocess`.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import warnings
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

    if config.grader.entrypoint:
        worker_python = grader_python_path(coral_dir)
        if not worker_python.exists():
            raise RuntimeError(
                f"Grader venv not initialized at {worker_python.parent}. "
                f"Run `coral validate` or `coral start` first so that "
                f"`coral.workspace.grader_env.setup_grader_env` can create it."
            )
        logger.info(
            f"Loading grader entrypoint {config.grader.entrypoint!r} "
            f"via worker {worker_python}"
        )
        return SubprocessGrader(
            entrypoint=config.grader.entrypoint,
            worker_python=worker_python,
            config=config.grader,
            private_dir=str(private_dir),
        )

    grader_path = private_dir / "eval" / "grader.py"
    if grader_path.exists():
        warnings.warn(
            "Loading grader from eval/grader.py is deprecated. Migrate to "
            "grader.entrypoint = 'your_pkg.module:Grader' in task.yaml and "
            "declare install steps under grader.setup. "
            "See docs/guides/custom-grader.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _load_eval_grader_py(grader_path, config, private_dir)

    raise ValueError(
        "No grader configured. Set grader.entrypoint = "
        "'your_pkg.module:Grader' in task.yaml (and grader.setup to install "
        "the package), or create eval/grader.py (deprecated)."
    )


def _load_eval_grader_py(grader_path: Path, config: CoralConfig, private_dir: Path) -> Any:
    """Legacy in-process load of eval/grader.py."""
    spec = importlib.util.spec_from_file_location("task_grader", str(grader_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load grader from {grader_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["task_grader"] = module
    spec.loader.exec_module(module)

    grader_cls = getattr(module, "Grader", None)
    if grader_cls is None:
        raise ImportError(
            f"eval/grader.py must export a class named 'Grader'. "
            f"Found: {[n for n in dir(module) if not n.startswith('_')]}"
        )

    from coral.grader.task_grader import TaskGrader

    if not issubclass(grader_cls, TaskGrader):
        raise TypeError(
            f"Grader class must inherit from TaskGrader, got {grader_cls.__bases__}"
        )

    grader = grader_cls(config=config.grader)
    grader.private_dir = str(private_dir)
    return grader
