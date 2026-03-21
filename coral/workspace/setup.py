"""Per-agent git worktrees, hook installation, symlinks."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from coral.config import CoralConfig

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


def _slugify(name: str) -> str:
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

    task_slug = _slugify(config.task.name)
    task_dir = results_dir / task_slug

    # Create timestamped run directory
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

    # Create/update "latest" symlink at task_dir/latest -> this run directory
    latest_link = task_dir / "latest"
    if latest_link.is_symlink():
        latest_link.unlink()
    if not latest_link.exists():
        rel = os.path.relpath(run_dir, task_dir)
        latest_link.symlink_to(rel)
        logger.info(f"Symlinked {latest_link} -> {rel}")

    # Clone source repo into run_dir/repo/
    repo_dir = _clone_or_init_repo(source_repo, run_repo)

    # Resolve task_dir (directory containing task.yaml)
    task_source_dir = config.task_dir or config_dir or Path.cwd()

    # Auto-copy eval/ to .coral/private/eval/ (if present in task directory)
    _copy_eval_to_private(task_source_dir, coral_dir)

    # Auto-detect and copy seed/ (if present in task directory and no explicit seed paths)
    if not config.task.seed:
        seed_dir = task_source_dir / "seed"
        if seed_dir.is_dir():
            _copy_seed_directory(seed_dir, repo_dir)

    # Copy explicit seed files into the repo
    if config.task.seed:
        _copy_seed_files(config.task.seed, repo_dir, config_dir or Path.cwd())

    # Copy private grader data into .coral/ (hidden from agents)
    if config.grader.private:
        _copy_private_data(config.grader.private, coral_dir, config_dir or Path.cwd())

    return ProjectPaths(
        results_dir=results_dir,
        task_dir=task_dir,
        run_dir=run_dir,
        coral_dir=coral_dir,
        agents_dir=agents_dir,
        repo_dir=repo_dir,
    )


def _copy_eval_to_private(task_dir: Path, coral_dir: Path) -> None:
    """Copy task's eval/ directory to .coral/private/eval/ (hidden from agents).

    This is where grader.py and any test data / answer keys live.
    """
    eval_src = task_dir / "eval"
    if not eval_src.is_dir():
        return

    eval_dst = coral_dir / "private" / "eval"
    if eval_dst.exists():
        shutil.rmtree(eval_dst)
    shutil.copytree(eval_src, eval_dst)
    logger.info(f"Copied eval/ to .coral/private/eval/ ({sum(1 for _ in eval_dst.rglob('*') if _.is_file())} files)")


def _copy_seed_directory(seed_dir: Path, repo_dir: Path) -> None:
    """Copy contents of seed/ directory into the repo root.

    Each item inside seed/ is copied to the repo root (not nested under seed/).
    """
    for item in seed_dir.iterdir():
        if item.name == "__pycache__":
            continue
        dst = repo_dir / item.name
        if item.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(item, dst)
            logger.info(f"Seeded directory: {item.name}/")
        else:
            shutil.copy2(item, dst)
            logger.info(f"Seeded file: {item.name}")

    # Stage and commit seed files
    subprocess.run(
        ["git", "-C", str(repo_dir), "add", "-A"],
        capture_output=True,
    )
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "diff", "--cached", "--quiet"],
        capture_output=True,
    )
    if result.returncode != 0:
        subprocess.run(
            ["git", "-C", str(repo_dir), "commit", "-m", "Add seed files"],
            capture_output=True,
        )
        logger.info("Committed seed files")


def _copy_seed_files(seed_paths: list[str], repo_dir: Path, config_dir: Path) -> None:
    """Copy seed files/directories into the repo.

    Paths in seed_paths are resolved relative to config_dir.
    Files are copied to the repo root. Directories are copied recursively.
    """
    for seed_path_str in seed_paths:
        src = Path(seed_path_str)
        if not src.is_absolute():
            src = (config_dir / src).resolve()

        if not src.exists():
            logger.warning(f"Seed path not found, skipping: {src}")
            continue

        dst = repo_dir / src.name
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            logger.info(f"Seeded directory: {src.name}/")
        else:
            shutil.copy2(src, dst)
            logger.info(f"Seeded file: {src.name}")

    # Stage and commit seed files
    subprocess.run(
        ["git", "-C", str(repo_dir), "add", "-A"],
        capture_output=True,
    )
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "diff", "--cached", "--quiet"],
        capture_output=True,
    )
    if result.returncode != 0:
        # There are staged changes
        subprocess.run(
            ["git", "-C", str(repo_dir), "commit", "-m", "Add seed files"],
            capture_output=True,
        )
        logger.info("Committed seed files")


def _copy_private_data(private_paths: list[str], coral_dir: Path, config_dir: Path) -> None:
    """Copy private grader data into .coral/ (hidden from agent worktrees).

    Paths are resolved relative to config_dir, same as seed paths.
    Files/dirs are placed under .coral/private/.
    """
    private_dir = coral_dir / "private"
    private_dir.mkdir(parents=True, exist_ok=True)

    for path_str in private_paths:
        src = Path(path_str)
        if not src.is_absolute():
            src = (config_dir / src).resolve()

        if not src.exists():
            logger.warning(f"Private data not found, skipping: {src}")
            continue

        dst = private_dir / src.name
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            logger.info(f"Private data directory: {src.name}/")
        else:
            shutil.copy2(src, dst)
            logger.info(f"Private data file: {src.name}")


def _clone_or_init_repo(source: Path, dest: Path) -> Path:
    """Clone source repo to dest, or init a new one if source doesn't exist.

    Uses git clone with --no-hardlinks so the clone is fully independent.
    Returns the path to the cloned repo.
    """
    if (source / ".git").exists():
        logger.info(f"Cloning {source} -> {dest}")
        result = subprocess.run(
            ["git", "clone", "--no-hardlinks", str(source), str(dest)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed: {result.stderr}")
        logger.debug(f"Clone: {result.stdout.strip()}")
        return dest

    if source.name.endswith(".git"):
        # Bare repo — clone it
        logger.info(f"Cloning bare repo {source} -> {dest}")
        result = subprocess.run(
            ["git", "clone", str(source), str(dest)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed: {result.stderr}")
        return dest

    # No git repo at source — init a fresh one at dest
    logger.info(f"No git repo at {source}, initializing fresh repo at {dest}")
    dest.mkdir(parents=True, exist_ok=True)

    # Copy source files if the directory has content
    if source.exists() and any(source.iterdir()):
        import shutil
        for item in source.iterdir():
            dst = dest / item.name
            if item.is_dir():
                shutil.copytree(item, dst)
            else:
                shutil.copy2(item, dst)

    subprocess.run(
        ["git", "init", str(dest)],
        capture_output=True, text=True, check=True,
    )
    subprocess.run(
        ["git", "-C", str(dest), "config", "user.email", "coral@local"],
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(dest), "config", "user.name", "CORAL"],
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(dest), "add", "-A"],
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(dest), "commit", "--allow-empty", "-m", "Initial commit"],
        capture_output=True,
    )
    return dest


def create_agent_worktree(repo_path: Path, agent_id: str, agents_dir: Path) -> Path:
    """Create a git worktree for an agent.

    Returns the worktree path.
    """
    worktree_path = agents_dir / agent_id

    if worktree_path.exists():
        logger.info(f"Worktree already exists at {worktree_path}, reusing")
        return worktree_path

    # Determine the git dir
    git_dir = repo_path / ".git" if (repo_path / ".git").exists() else repo_path
    logger.debug(f"git_dir={git_dir}")

    branch_name = f"coral/{agent_id}"

    # Get current HEAD
    result = subprocess.run(
        ["git", "--git-dir", str(git_dir), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )

    if result.returncode == 0:
        head = result.stdout.strip()
        logger.debug(f"HEAD={head[:12]}, creating branch {branch_name}")
        result = subprocess.run(
            ["git", "--git-dir", str(git_dir), "branch", branch_name, head],
            capture_output=True, text=True,
        )
        if result.returncode != 0 and "already exists" not in result.stderr:
            logger.warning(f"Branch creation: {result.stderr.strip()}")
    else:
        # No commits yet — create an initial commit
        logger.info("No commits found, creating initial empty commit")
        subprocess.run(
            ["git", "--git-dir", str(git_dir), "--work-tree", str(repo_path),
             "commit", "--allow-empty", "-m", "Initial commit"],
            capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "--git-dir", str(git_dir), "branch", branch_name],
            capture_output=True, text=True,
        )

    # Create worktree
    logger.info(f"Creating worktree at {worktree_path} on branch {branch_name}")
    result = subprocess.run(
        ["git", "--git-dir", str(git_dir), "worktree", "add", str(worktree_path), branch_name],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git worktree add failed:\n"
            f"  git_dir: {git_dir}\n"
            f"  worktree: {worktree_path}\n"
            f"  branch: {branch_name}\n"
            f"  stderr: {result.stderr}"
        )
    logger.debug(f"Worktree created: {result.stdout.strip()}")

    return worktree_path


def setup_gitignore(worktree_path: Path) -> None:
    """Write .gitignore to exclude CORAL-managed files from git."""
    gitignore_path = worktree_path / ".gitignore"
    entries = {".coral_agent_id", ".coral_dir", "CLAUDE.md", "AGENTS.md", ".claude/", ".codex/", ".opencode/"}

    # Preserve existing entries
    existing = set()
    if gitignore_path.exists():
        existing = set(gitignore_path.read_text().splitlines())

    missing = entries - existing
    if missing:
        with gitignore_path.open("a") as f:
            for entry in sorted(missing):
                f.write(f"{entry}\n")


def write_agent_id(worktree_path: Path, agent_id: str) -> None:
    """Write .coral_agent_id file in the worktree."""
    (worktree_path / ".coral_agent_id").write_text(agent_id)


def write_coral_dir(worktree_path: Path, coral_dir: Path) -> None:
    """Write .coral_dir breadcrumb storing the absolute path to the shared .coral directory.

    Hooks and graders read this file to locate shared state (attempts, config,
    private grader data) without needing a symlink in the worktree.
    """
    (worktree_path / ".coral_dir").write_text(str(coral_dir.resolve()))


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


def get_coral_dir(worktree_path: Path) -> Path | None:
    """Read the shared .coral directory path from the .coral_dir breadcrumb file."""
    ref_file = worktree_path / ".coral_dir"
    if ref_file.exists():
        return Path(ref_file.read_text().strip())
    return None


def setup_shared_state(worktree_path: Path, coral_dir: Path, shared_dir_name: str = ".claude") -> None:
    """Create a shared state directory in the worktree with symlinks to .coral/public/.

    Symlinks notes, skills, attempts, and logs from .coral/public/ into
    the shared directory so agents can read/write shared state.

    Args:
        worktree_path: Path to the agent's git worktree
        coral_dir: Path to the shared .coral directory
        shared_dir_name: Name of the shared dir in the worktree (e.g. ".claude", ".codex", ".opencode")
    """
    coral_public = coral_dir / "public"

    shared_dir = worktree_path / shared_dir_name

    # If it's an old-style symlink to .coral/public/, replace with a real directory.
    if shared_dir.is_symlink():
        shared_dir.unlink()

    shared_dir.mkdir(exist_ok=True)

    # Symlink shared content from .coral/public/
    shared_items = [
        "notes",
        "skills",
        "attempts",
        "logs",
        "heartbeat",
    ]
    for item in shared_items:
        src = coral_public / item
        dst = shared_dir / item
        if not dst.exists() and not dst.is_symlink():
            try:
                rel = os.path.relpath(src.resolve(), shared_dir.resolve())
                dst.symlink_to(rel)
            except (ValueError, OSError):
                dst.symlink_to(src.resolve())


def setup_claude_settings(worktree_path: Path, coral_dir: Path, *, research: bool = True) -> None:
    """Write Claude Code settings.json with permissions.

    Grants the agent all tool permissions via allow rules (replacing
    --dangerously-skip-permissions).
    """
    claude_dir = worktree_path / ".claude"
    claude_dir.mkdir(exist_ok=True)

    private_dir = str(coral_dir.resolve() / "private")
    agents_dir = str(coral_dir.resolve().parent / "agents")
    worktree_str = str(worktree_path.resolve())
    private_pattern = f"{private_dir}/**"
    agents_pattern = f"{agents_dir}/**"
    worktree_pattern = f"{worktree_str}/**"

    # Allow rules grant agent autonomy without --dangerously-skip-permissions
    # Bash/Edit/Write are scoped to the agent's own worktree via allow + deny rules
    allow_rules: list[str] = [
        "Bash",
        f"Read(/{worktree_pattern})",
        f"Read(/{agents_pattern})",
        f"Edit(/{worktree_pattern})",
        f"Write(/{worktree_pattern})",
    ]
    if research:
        allow_rules.extend(["WebSearch", "WebFetch"])

    # Deny rules block git and private dir access.
    # Edit/Write/Bash don't need agents_pattern denies — the scoped allows
    # already restrict them to the agent's own worktree.
    deny_rules: list[str] = [
        "Bash(git *)",
        f"Read(/{private_pattern})",
    ]
    if not research:
        deny_rules.extend(["WebSearch", "WebFetch"])

    settings: dict = {
        "permissions": {
            "allow": allow_rules,
            "deny": deny_rules,
        },
    }

    settings_path = claude_dir / "settings.json"
    # Always overwrite — each agent needs its own copy
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")

