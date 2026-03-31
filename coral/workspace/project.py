"""Project-level directory structure and orchestration."""

from __future__ import annotations

import logging
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from coral.config import CoralConfig
from coral.hub.checkpoint import init_checkpoint_repo
from coral.workspace.repo import (
    clone_or_init_repo,
    copy_eval_to_private,
    copy_private_data,
    copy_seed_directory,
    copy_seed_files,
)

logger = logging.getLogger(__name__)


@dataclass
class ProjectPaths:
    """Paths created by create_project."""

    results_dir: Path   # e.g. results/
    task_dir: Path      # e.g. results/erdos-minimum-overlap-problem/
    run_dir: Path       # e.g. results/erdos-minimum-overlap-problem/2026-03-11_163000/
    coral_dir: Path     # run_dir/.coral/
    agents_dir: Path    # run_dir/agents/
    repo_dir: Path      # run_dir/repo/ (cloned per-run)


def slugify(name: str) -> str:
    """Convert a task name to a filesystem-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "task"


_SEED_SKILLS_DIR = Path(__file__).parent.parent / "template" / "skills"


def create_project(config: CoralConfig, config_dir: Path | None = None) -> ProjectPaths:
    """Create the full project directory structure.

    Each run gets its own clone of the source repo so runs are fully independent.

    Layout:
        results/
        └── <task-slug>/
            ├── latest -> 2026-03-11_163000   (symlink)
            └── <timestamp>/
                ├── .coral/
                │   ├── public/          # contents symlinked into .claude/ in worktrees
                │   │   ├── CLAUDE.md
                │   │   ├── notes/
                │   │   ├── change_summary.md
                │   │   ├── skills/
                │   │   ├── attempts/
                │   │   ├── logs/
                │   │   └── settings.json
                │   ├── private/
                │   └── config.yaml
                ├── repo/                # cloned from source
                └── agents/              # worktrees off repo/
    """
    results_dir = Path(config.workspace.results_dir).resolve()
    source_repo = Path(config.workspace.repo_path).resolve()

    task_slug = slugify(config.task.name)
    task_dir = results_dir / task_slug

    # Use explicit run_dir if provided, otherwise generate timestamped one
    if config.workspace.run_dir:
        run_dir = Path(config.workspace.run_dir).resolve()
        task_dir = run_dir.parent
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        run_dir = task_dir / timestamp
    coral_dir = run_dir / ".coral"
    agents_dir = run_dir / "agents"
    run_repo = run_dir / "repo"

    logger.debug(f"results_dir={results_dir}, task_dir={task_dir}, run_dir={run_dir}")

    # Create shared state directories
    (coral_dir / "public").mkdir(parents=True, exist_ok=True)
    (coral_dir / "public" / "attempts").mkdir(parents=True, exist_ok=True)
    (coral_dir / "public" / "logs").mkdir(parents=True, exist_ok=True)
    (coral_dir / "public" / "skills").mkdir(parents=True, exist_ok=True)
    (coral_dir / "public" / "notes").mkdir(parents=True, exist_ok=True)
    (coral_dir / "public" / "heartbeat").mkdir(parents=True, exist_ok=True)
    (coral_dir / "private").mkdir(parents=True, exist_ok=True)
    agents_dir.mkdir(parents=True, exist_ok=True)

    # Initialize checkpoint repo for shared state versioning
    init_checkpoint_repo(str(coral_dir))

    # Seed bundled skills from coral/template/skills/
    seed_skills_dir = _SEED_SKILLS_DIR
    if seed_skills_dir.is_dir():
        for skill_dir in seed_skills_dir.iterdir():
            if skill_dir.is_dir():
                dst = coral_dir / "public" / "skills" / skill_dir.name
                if not dst.exists():
                    shutil.copytree(skill_dir, dst)
                    logger.info(f"Seeded skill: {skill_dir.name}")

    # Save config
    config.to_yaml(coral_dir / "config.yaml")

    # Save config_dir so resume can restore task_dir for relative path resolution
    effective_config_dir = config.task_dir or config_dir or Path.cwd()
    (coral_dir / "config_dir").write_text(str(effective_config_dir))

    # Create/update "latest" symlink at task_dir/latest -> this run directory
    latest_link = task_dir / "latest"
    if latest_link.is_symlink():
        latest_link.unlink()
    if not latest_link.exists():
        rel = os.path.relpath(run_dir, task_dir)
        latest_link.symlink_to(rel)
        logger.info(f"Symlinked {latest_link} -> {rel}")

    # Clone source repo into run_dir/repo/
    repo_dir = clone_or_init_repo(source_repo, run_repo)

    # Resolve task_dir (directory containing task.yaml)
    task_source_dir = config.task_dir or config_dir or Path.cwd()

    # Auto-copy eval/ to .coral/private/eval/ (if present in task directory)
    copy_eval_to_private(task_source_dir, coral_dir)

    # Auto-detect and copy seed/ (if present in task directory and no explicit seed paths)
    if not config.task.seed:
        seed_dir = task_source_dir / "seed"
        if seed_dir.is_dir():
            copy_seed_directory(seed_dir, repo_dir)

    # Copy explicit seed files into the repo
    if config.task.seed:
        copy_seed_files(config.task.seed, repo_dir, config_dir or Path.cwd())

    # Copy private grader data into .coral/ (hidden from agents)
    if config.grader.private:
        copy_private_data(config.grader.private, coral_dir, config_dir or Path.cwd())

    return ProjectPaths(
        results_dir=results_dir,
        task_dir=task_dir,
        run_dir=run_dir,
        coral_dir=coral_dir,
        agents_dir=agents_dir,
        repo_dir=repo_dir,
    )


def reconstruct_paths(coral_dir: Path) -> ProjectPaths:
    """Reconstruct ProjectPaths from an existing .coral directory.

    Used by `coral resume` to rebuild paths without creating a new run.
    """
    coral_dir = coral_dir.resolve()
    run_dir = coral_dir.parent
    task_dir = run_dir.parent
    results_dir = task_dir.parent

    return ProjectPaths(
        results_dir=results_dir,
        task_dir=task_dir,
        run_dir=run_dir,
        coral_dir=coral_dir,
        agents_dir=run_dir / "agents",
        repo_dir=run_dir / "repo",
    )
