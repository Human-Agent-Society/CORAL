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
        return _load_legacy_grader(config, coral_dir)

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


def _load_legacy_grader(config: CoralConfig, coral_dir: Path | None = None) -> Any:
    """Legacy grader loading by type name."""
    private_dir = (coral_dir / "private") if coral_dir else None
    grader_type = config.grader.type

    if grader_type == "function":
        module_path = config.grader.module
        if not module_path:
            raise ValueError("Function grader requires 'module' in grader config")
        mod = importlib.import_module(module_path)
        func = getattr(mod, config.grader.args.get("func_name", "grade"))
        from coral.grader.builtin.function_grader import FunctionGrader
        return FunctionGrader(name="eval", func=func)

    elif grader_type in ("rubric_judge", "strict_rubric_judge", "scored_rubric_judge",
                         "dynamic_rubric_judge", "race_rubric_judge", "agent_judge"):
        return _load_rubric_grader(config, grader_type, private_dir)

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


def _load_rubric_grader(config: CoralConfig, grader_type: str, private_dir: Path | None) -> Any:
    """Load a rubric-based judge grader by type."""
    from coral.config import GraderConfig, RubricItem

    rubrics = config.task.rubrics if hasattr(config.task, "rubrics") and config.task.rubrics else []
    if not rubrics:
        rubrics_raw = config.grader.args.get("rubrics", [])
        rubrics = [
            RubricItem(name=r["name"], description=r["description"], weight=r.get("weight", 1.0))
            for r in rubrics_raw
        ]

    grader_args = dict(config.grader.args)
    grader_args.pop("rubrics", None)
    grader_args.setdefault("task_description", config.task.description)
    grader_args.setdefault("files", config.task.files)

    grader_config = GraderConfig(
        type=config.grader.type,
        module=config.grader.module,
        timeout=config.grader.timeout,
        args=grader_args,
        private=config.grader.private,
        direction=config.grader.direction,
    )

    # Import the right grader class
    grader_classes = {
        "rubric_judge": ("coral.grader.builtin.rubric_judge_grader", "RubricJudgeGrader"),
        "strict_rubric_judge": ("coral.grader.builtin.strict_rubric_judge_grader", "StrictRubricJudgeGrader"),
        "scored_rubric_judge": ("coral.grader.builtin.scored_rubric_judge_grader", "ScoredRubricJudgeGrader"),
        "dynamic_rubric_judge": ("coral.grader.builtin.dynamic_rubric_judge_grader", "DynamicRubricJudgeGrader"),
        "race_rubric_judge": ("coral.grader.builtin.race_rubric_judge_grader", "RaceRubricJudgeGrader"),
        "agent_judge": ("coral.grader.builtin.agent_judge_grader", "AgentJudgeGrader"),
    }

    module_path, class_name = grader_classes[grader_type]
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)

    if grader_type == "agent_judge":
        grader_args.setdefault("task_name", config.task.name)
        grader_config = GraderConfig(
            type=config.grader.type, module=config.grader.module,
            timeout=config.grader.timeout, args=grader_args,
            private=config.grader.private, direction=config.grader.direction,
        )

    grader = cls(config=grader_config, rubrics=rubrics)
    if private_dir:
        grader.private_dir = str(private_dir)
    return grader
