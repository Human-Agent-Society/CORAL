"""Task validation — checks that a task directory is well-formed.

Called automatically by `coral start` and `coral validate`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coral.config import CoralConfig


def validate_task(task_dir: Path, *, repo_base_dir: Path | None = None) -> list[str]:
    """Validate a task directory. Returns a list of error strings (empty = valid)."""
    errors: list[str] = []
    repo_base_dir = repo_base_dir or task_dir

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

    # 4. Extra private files exist if specified
    private_paths: list[tuple[str, Path]] = []
    for private_path in config.grader.private:
        p = Path(private_path)
        if not p.is_absolute():
            p = task_dir / p
        resolved = p.expanduser().resolve()
        private_paths.append((private_path, resolved))
        if not p.exists():
            errors.append(f"Private file not found: {private_path}")

    _validate_private_not_reexposed(config, task_dir, private_paths, errors, repo_base_dir)

    return errors


def _validate_private_not_reexposed(
    config: CoralConfig,
    task_dir: Path,
    private_paths: list[tuple[str, Path]],
    errors: list[str],
    repo_base_dir: Path,
) -> None:
    if not private_paths:
        return

    repo_path = _resolve_path(config.workspace.repo_path or ".", repo_base_dir)
    for private_raw, private_path in private_paths:
        if _paths_overlap(repo_path, private_path):
            errors.append(
                f"grader.private path {private_raw!r} overlaps workspace.repo_path "
                f"{config.workspace.repo_path!r}; agents can read workspace.repo_path. "
                "Move hidden files outside the agent repo (for example keep "
                "workspace.repo_path: seed) or remove them from grader.private."
            )

    for label, raw_source in _agent_visible_sources(config):
        source = _resolve_path(raw_source, task_dir)
        for private_raw, private_path in private_paths:
            if _paths_overlap(source, private_path):
                errors.append(
                    f"{label} source {raw_source!r} overlaps grader.private path "
                    f"{private_raw!r}; this would make hidden data visible to agents."
                )


def _agent_visible_sources(config: CoralConfig) -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []

    def collect(prefix: str, runtime_options: dict[str, Any]) -> None:
        mounts = runtime_options.get("mounts") or {}
        if isinstance(mounts, dict):
            for source in mounts:
                sources.append((f"{prefix}.mounts", str(source)))

        for source in runtime_options.get("add_dirs") or []:
            sources.append((f"{prefix}.add_dirs", str(source)))

        role_file = runtime_options.get("role_file")
        if role_file:
            sources.append((f"{prefix}.role_file", str(role_file)))

    collect("agents.runtime_options", config.agents.runtime_options)
    for idx, assignment in enumerate(config.agents.assignments):
        collect(f"agents.assignments[{idx}].runtime_options", assignment.runtime_options)
    return sources


def _resolve_path(raw: str | Path, base_dir: Path) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _paths_overlap(left: Path, right: Path) -> bool:
    return _is_within(left, right) or _is_within(right, left)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
