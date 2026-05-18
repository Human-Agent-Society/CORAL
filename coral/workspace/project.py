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
_SEED_AGENTS_DIR = Path(__file__).parent.parent / "template" / "agents"
_IDENTITY_TEMPLATE_PATH = Path(__file__).parent.parent / "template" / "identity_template.md"


def seed_agent_identity(
    coral_dir: Path,
    agent_id: str,
    source: str | None = None,
    base_dir: Path | None = None,
) -> Path:
    """Write the per-agent identity certificate at .coral/public/identities/<agent_id>.md.

    Idempotent: does nothing if the file already exists, so an agent's evolved
    certificate is never clobbered by a re-setup or resume.

    When ``source`` is None (the default), renders the bundled gen-0 identity
    template — every agent starts with a blank certificate they earn into.

    When ``source`` is set, copies that user-provided .md file as-is, giving
    each agent a custom starting posture. ``source`` is a host path with ``~``
    expansion; resolved against ``base_dir`` (typically the task directory)
    when not absolute. Matches the path convention of ``apply_runtime_mounts``.

    Raises:
        FileNotFoundError: if ``source`` is given but does not resolve to a file.
        ValueError: if ``source`` is given but ``base_dir`` is None and ``source``
            is a relative path.
    """
    identities_dir = coral_dir / "public" / "identities"
    identities_dir.mkdir(parents=True, exist_ok=True)
    dst = identities_dir / f"{agent_id}.md"
    if dst.exists():
        return dst

    if source is None:
        template = _IDENTITY_TEMPLATE_PATH.read_text()
        rendered = template.format(
            agent_id=agent_id,
            created_at=datetime.now().isoformat(),
        )
        dst.write_text(rendered)
        return dst

    src = Path(source).expanduser()
    if not src.is_absolute():
        if base_dir is None:
            raise ValueError(
                f"identity_file {source!r} is relative; base_dir is required to resolve it"
            )
        src = (base_dir / src).resolve()
    if not src.is_file():
        raise FileNotFoundError(
            f"identity_file {source!r} (resolved to {src}) does not exist"
        )
    shutil.copy2(src, dst)
    return dst


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
                │   │   ├── agents/
                │   │   ├── attempts/
                │   │   ├── logs/
                │   │   └── settings.local.json
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
    (coral_dir / "public" / "agents").mkdir(parents=True, exist_ok=True)
    (coral_dir / "public" / "notes").mkdir(parents=True, exist_ok=True)
    (coral_dir / "public" / "heartbeat").mkdir(parents=True, exist_ok=True)
    (coral_dir / "public" / "eval_logs").mkdir(parents=True, exist_ok=True)
    (coral_dir / "public" / "identities").mkdir(parents=True, exist_ok=True)
    (coral_dir / "private").mkdir(parents=True, exist_ok=True)
    agents_dir.mkdir(parents=True, exist_ok=True)

    # Initialize checkpoint repo for shared state versioning
    init_checkpoint_repo(str(coral_dir))

    # Resolve task directory for relative path resolution
    effective_config_dir = config.task_dir or config_dir or Path.cwd()

    # Seed bundled skills from coral/template/skills/
    seed_skills_dir = _SEED_SKILLS_DIR
    if seed_skills_dir.is_dir():
        for skill_dir in seed_skills_dir.iterdir():
            if skill_dir.is_dir():
                dst = coral_dir / "public" / "skills" / skill_dir.name
                if not dst.exists():
                    shutil.copytree(skill_dir, dst)
                    logger.info(f"Seeded skill: {skill_dir.name}")

    # Seed user-provided skills from agents.skills config
    for skill_path in config.agents.skills:
        src = Path(skill_path)
        if not src.is_absolute():
            src = (effective_config_dir / src).resolve()
        if src.is_dir():
            dst = coral_dir / "public" / "skills" / src.name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            logger.info(f"Seeded user skill: {src.name}")
        else:
            logger.warning(f"Skill directory not found: {src}")

    # Seed bundled agent templates from coral/template/agents/
    seed_agents_dir = _SEED_AGENTS_DIR
    if seed_agents_dir.is_dir():
        for agent_file in seed_agents_dir.iterdir():
            if agent_file.is_file():
                dst = coral_dir / "public" / "agents" / agent_file.name
                if not dst.exists():
                    shutil.copy2(agent_file, dst)
                    logger.info(f"Seeded agent template: {agent_file.name}")

    # Save config
    config.to_yaml(coral_dir / "config.yaml")

    # Save config_dir so resume can restore task_dir for relative path resolution
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

    # Auto-copy seed/ into repo (if present in task directory)
    seed_dir = task_source_dir / "seed"
    if seed_dir.is_dir():
        copy_seed_directory(seed_dir, repo_dir)

    # Copy private grader data into .coral/ (hidden from agents)
    if config.grader.private:
        copy_private_data(config.grader.private, coral_dir, config_dir or Path.cwd())

    # Bootstrap the grader's isolated venv at .coral/private/grader_venv/ and
    # run any user-supplied install steps. Skipped when the task is still on the
    # legacy eval/grader.py (in-process) path.
    if config.grader.entrypoint:
        from coral.workspace.grader_env import setup_grader_env

        setup_grader_env(coral_dir, config.grader, config_dir or Path.cwd())

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
