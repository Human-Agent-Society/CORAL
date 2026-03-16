"""Task validation — checks that a task directory is well-formed.

Called automatically by `coral start` and `coral validate`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from coral.config import CoralConfig


def validate_task(task_dir: Path) -> list[str]:
    """Validate a task directory. Returns a list of error strings (empty = valid)."""
    errors: list[str] = []

    # 1. task.yaml exists and parses
    task_yaml = task_dir / "task.yaml"
    if not task_yaml.exists():
        errors.append(f"task.yaml not found in {task_dir}")
        return errors  # Can't continue without config

    try:
        config = CoralConfig.from_yaml(task_yaml)
    except Exception as e:
        errors.append(f"task.yaml parse error: {e}")
        return errors

    # 2. eval/grader.py exists (if no legacy grader.type is set)
    eval_dir = task_dir / "eval"
    grader_py = eval_dir / "grader.py"
    has_eval_grader = grader_py.exists()

    if not has_eval_grader and not config.grader.type:
        errors.append(
            "eval/grader.py not found and no grader.type specified in task.yaml. "
            "Either create eval/grader.py or set grader.type for a legacy builtin."
        )

    # 3. grader.py exports a Grader class that inherits from TaskGrader
    if has_eval_grader:
        try:
            spec = importlib.util.spec_from_file_location("task_grader_check", str(grader_py))
            if spec is None or spec.loader is None:
                errors.append("Cannot load eval/grader.py")
            else:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                grader_cls = getattr(module, "Grader", None)
                if grader_cls is None:
                    errors.append("eval/grader.py must export a class named 'Grader'")
                else:
                    from coral.grader.task_grader import TaskGrader
                    if not issubclass(grader_cls, TaskGrader):
                        errors.append(
                            f"Grader class must inherit from TaskGrader, "
                            f"got bases: {[b.__name__ for b in grader_cls.__bases__]}"
                        )
        except Exception as e:
            errors.append(f"eval/grader.py import error: {e}")

    # 4. direction is valid
    if config.grader.direction not in ("maximize", "minimize"):
        errors.append(
            f"grader.direction must be 'maximize' or 'minimize', "
            f"got '{config.grader.direction}'"
        )

    # 5. Extra private files exist if specified
    for private_path in config.grader.private:
        p = Path(private_path)
        if not p.is_absolute():
            p = task_dir / p
        if not p.exists():
            errors.append(f"Private file not found: {private_path}")

    return errors
