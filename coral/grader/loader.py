"""Convention-based grader discovery from task eval/ directories.

Loads eval/grader.py from .coral/private/eval/, finds the Grader class
(must be a TaskGrader subclass), and instantiates it with config args.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from coral.config import CoralConfig

logger = logging.getLogger(__name__)


def load_grader(config: CoralConfig, coral_dir: str | Path) -> Any:
    """Load a grader from the task's eval/grader.py in .coral/private/eval/.

    Falls back to legacy builtin graders if config.grader.type is set.
    """
    coral_dir = Path(coral_dir)
    private_dir = coral_dir / "private"
    grader_path = private_dir / "eval" / "grader.py"

    if not grader_path.exists():
        # Fallback: load builtin grader by type name
        return _load_legacy_grader(config)

    # Import grader.py dynamically
    spec = importlib.util.spec_from_file_location("task_grader", str(grader_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load grader from {grader_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["task_grader"] = module
    spec.loader.exec_module(module)

    # Find the Grader class
    grader_cls = getattr(module, "Grader", None)
    if grader_cls is None:
        raise ImportError(
            f"eval/grader.py must export a class named 'Grader'. "
            f"Found: {[n for n in dir(module) if not n.startswith('_')]}"
        )

    from coral.grader.task_grader import TaskGrader

    if not issubclass(grader_cls, TaskGrader):
        raise TypeError(
            f"Grader class must inherit from TaskGrader, "
            f"got {grader_cls.__bases__}"
        )

    # Instantiate with grader config
    grader = grader_cls(config=config.grader)
    grader.private_dir = str(private_dir)

    logger.info(f"Loaded grader from {grader_path}")
    return grader


def _load_legacy_grader(config: CoralConfig) -> Any:
    """Legacy grader loading for backward compatibility (function grader only)."""
    grader_type = config.grader.type

    if grader_type == "function":
        module_path = config.grader.module
        if not module_path:
            raise ValueError("Function grader requires 'module' in grader config")
        mod = importlib.import_module(module_path)
        func = getattr(mod, config.grader.args.get("func_name", "grade"))
        from coral.grader.builtin.function_grader import FunctionGrader
        return FunctionGrader(name="eval", func=func)

    elif grader_type and config.grader.module:
        # Generic module-based loading
        mod = importlib.import_module(config.grader.module)
        cls = getattr(mod, config.grader.type)
        return cls(**config.grader.args)

    else:
        raise ValueError(
            f"No eval/grader.py found in .coral/private/eval/ and no valid "
            f"legacy grader type specified (got type={config.grader.type!r}). "
            f"Either create eval/grader.py in your task directory or set "
            f"grader.type and grader.module in task.yaml."
        )
