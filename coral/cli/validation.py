"""Task validation — checks that a task directory is well-formed.

Called automatically by `coral start` and `coral validate`.
"""

from __future__ import annotations

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

    # 2. grader.entrypoint is set and well-formed.
    if not config.grader.entrypoint:
        errors.append(
            "No grader configured. Set grader.entrypoint = "
            "'your_pkg.module:Grader' in task.yaml and grader.setup to "
            "install the package."
        )
    elif ":" not in config.grader.entrypoint:
        errors.append(
            f"grader.entrypoint must be 'module.path:ClassName', got {config.grader.entrypoint!r}"
        )

    # 3. direction is valid
    if config.grader.direction not in ("maximize", "minimize"):
        errors.append(
            f"grader.direction must be 'maximize' or 'minimize', got '{config.grader.direction}'"
        )

    # 4. Extra private files exist, and are NOT inside the grader package.
    # The grader package (task_dir/grader) is surfaced read-only to agents at
    # <shared_dir>/grader/, so a grader.private path living inside it would be
    # both copied to .coral/private/ AND exposed via the surfaced source — a
    # leak. Hidden inputs must sit outside the grader dir (e.g. a sibling
    # ``taskdata/`` declared as ``taskdata``).
    grader_dir = (task_dir / "grader").resolve()
    for private_path in config.grader.private:
        p = Path(private_path)
        if not p.is_absolute():
            p = task_dir / p
        if not p.exists():
            errors.append(f"Private file not found: {private_path}")
            continue
        try:
            p.resolve().relative_to(grader_dir)
        except ValueError:
            pass  # outside the grader package — good
        else:
            errors.append(
                f"grader.private path '{private_path}' is inside the grader package "
                f"(grader/), which is surfaced read-only to agents at "
                f"<shared_dir>/grader/ — this would leak it. Move it outside grader/ "
                f"(e.g. a sibling 'taskdata/')."
            )

    return errors
