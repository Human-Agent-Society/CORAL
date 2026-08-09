"""Per-agent git worktree creation, shared state, and permissions."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from coral.venv_paths import venv_python as resolve_venv_python
from coral.workspace.repo import (
    _clean_env,
    run_setup_commands,
)

logger = logging.getLogger(__name__)


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
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        head = result.stdout.strip()
        logger.debug(f"HEAD={head[:12]}, creating branch {branch_name}")
        result = subprocess.run(
            ["git", "--git-dir", str(git_dir), "branch", branch_name, head],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 and "already exists" not in result.stderr:
            logger.warning(f"Branch creation: {result.stderr.strip()}")
    else:
        # No commits yet — create an initial commit
        logger.info("No commits found, creating initial empty commit")
        subprocess.run(
            [
                "git",
                "--git-dir",
                str(git_dir),
                "--work-tree",
                str(repo_path),
                "commit",
                "--allow-empty",
                "-m",
                "Initial commit",
            ],
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "--git-dir", str(git_dir), "branch", branch_name],
            capture_output=True,
            text=True,
        )

    # Create worktree
    logger.info(f"Creating worktree at {worktree_path} on branch {branch_name}")
    result = subprocess.run(
        ["git", "--git-dir", str(git_dir), "worktree", "add", str(worktree_path), branch_name],
        capture_output=True,
        text=True,
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


def setup_git_exclude(worktree_path: Path) -> None:
    """Register CORAL-managed files in the repo's git exclude file."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        cwd=worktree_path,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git rev-parse --git-common-dir failed in {worktree_path}: {result.stderr}"
        )
    common_dir = (worktree_path / result.stdout.strip()).resolve()
    exclude_path = common_dir / "info" / "exclude"

    entries = {
        ".coral_agent_id",
        ".coral_dir",
        ".coral_island",
        ".coral_setup_complete",
        "CLAUDE.md",
        "AGENTS.md",
        ".claude/",
        ".codex/",
        ".cursor/",
        ".opencode/",
        ".pi/",
        ".venv/",
    }

    existing = set()
    if exclude_path.exists():
        existing = set(exclude_path.read_text(encoding="utf-8").splitlines())

    missing = entries - existing
    if missing:
        exclude_path.parent.mkdir(parents=True, exist_ok=True)
        with exclude_path.open("a", encoding="utf-8") as f:
            for entry in sorted(missing):
                f.write(f"{entry}\n")


def write_agent_id(worktree_path: Path, agent_id: str) -> None:
    """Write .coral_agent_id file in the worktree."""
    (worktree_path / ".coral_agent_id").write_text(agent_id, encoding="utf-8")


def write_coral_dir(worktree_path: Path, coral_dir: Path) -> None:
    """Write .coral_dir breadcrumb storing the absolute path to the shared .coral directory."""
    (worktree_path / ".coral_dir").write_text(str(coral_dir.resolve()), encoding="utf-8")


def get_coral_dir(worktree_path: Path) -> Path | None:
    """Read the shared .coral directory path from the .coral_dir breadcrumb file."""
    ref_file = worktree_path / ".coral_dir"
    if ref_file.exists():
        return Path(ref_file.read_text(encoding="utf-8").strip())
    return None


def grader_source_dir(coral_dir: Path) -> Path | None:
    """Resolve the task's grader package dir ({config_dir}/grader), or None."""
    cfg_file = coral_dir / "config_dir"
    if not cfg_file.exists():
        return None
    grader = Path(cfg_file.read_text(encoding="utf-8").strip()) / "grader"
    return grader if grader.is_dir() else None


def setup_shared_state(
    worktree_path: Path,
    coral_dir: Path,
    shared_dir_name: str = ".claude",
    island_id: str | int | None = None,
) -> None:
    """Create a shared state directory in the worktree with symlinks into the island root."""
    from coral.hub._island import island_root

    state_root = island_root(coral_dir, island_id)
    shared_dir = worktree_path / shared_dir_name

    if shared_dir.is_symlink():
        shared_dir.unlink()

    shared_dir.mkdir(exist_ok=True)

    for item in _SHARED_STATE_ITEMS:
        src = state_root / item
        dst = shared_dir / item
        if dst.exists() and not dst.is_symlink() and dst.is_dir():
            src.mkdir(parents=True, exist_ok=True)
            for entry in dst.iterdir():
                target = src / entry.name
                if not target.exists():
                    shutil.move(str(entry), str(target))
            try:
                dst.rmdir()
            except OSError:
                continue
        if not dst.exists() and not dst.is_symlink():
            try:
                rel = os.path.relpath(src.resolve(), shared_dir.resolve())
                dst.symlink_to(rel)
            except (ValueError, OSError):
                dst.symlink_to(src.resolve())

    grader_source = grader_source_dir(coral_dir)
    if grader_source is not None:
        grader_dst = shared_dir / "grader"
        if not grader_dst.exists() and not grader_dst.is_symlink():
            grader_dst.symlink_to(grader_source.resolve())

    if island_id is not None:
        (worktree_path / ".coral_island").write_text(str(island_id), encoding="utf-8")


_SHARED_STATE_ITEMS: tuple[str, ...] = (
    "notes",
    "skills",
    "agents",
    "attempts",
    "logs",
    "heartbeat",
    "roles",
    "eval_logs",
)


def repoint_shared_state(
    worktree_path: Path,
    coral_dir: Path,
    shared_dir_name: str,
    new_island_id: str | int,
) -> None:
    """Repoint an agent's shared-state symlinks at a different island."""
    from coral.hub._island import island_root

    if new_island_id is None:
        raise ValueError("repoint_shared_state requires a non-None new_island_id")

    state_root = island_root(coral_dir, new_island_id)
    shared_dir = worktree_path / shared_dir_name
    shared_dir.mkdir(exist_ok=True)

    for item in _SHARED_STATE_ITEMS:
        src = state_root / item
        dst = shared_dir / item
        src.mkdir(parents=True, exist_ok=True)

        if dst.is_symlink():
            dst.unlink()
        elif dst.exists() and dst.is_dir():
            for entry in dst.iterdir():
                target = src / entry.name
                if not target.exists():
                    shutil.move(str(entry), str(target))
            try:
                dst.rmdir()
            except OSError:
                logger.warning(f"repoint_shared_state: could not remove non-empty local dir {dst}")
                continue

        try:
            rel = os.path.relpath(src.resolve(), shared_dir.resolve())
            dst.symlink_to(rel)
        except (ValueError, OSError):
            dst.symlink_to(src.resolve())

    (worktree_path / ".coral_island").write_text(str(new_island_id), encoding="utf-8")


def apply_runtime_mounts(
    worktree_path: Path,
    mounts: dict[str, str],
    base_dir: Path,
) -> None:
    """Copy host files into the agent worktree per runtime_options.mounts."""
    if not mounts:
        return
    worktree_resolved = worktree_path.resolve()
    for source_raw, dest_raw in mounts.items():
        source = Path(source_raw).expanduser()
        if not source.is_absolute():
            source = (base_dir / source).resolve()
        if not source.exists():
            raise FileNotFoundError(
                f"mount source {source_raw!r} (resolved to {source}) does not exist"
            )

        dest_path = Path(dest_raw)
        if dest_path.is_absolute():
            raise ValueError(f"mount dest {dest_raw!r} must be worktree-relative, not absolute")
        dest = (worktree_resolved / dest_path).resolve()
        try:
            dest.relative_to(worktree_resolved)
        except ValueError as e:
            raise ValueError(f"mount dest {dest_raw!r} escapes worktree {worktree_path}") from e

        dest.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            if dest.exists() or dest.is_symlink():
                if dest.is_dir() and not dest.is_symlink():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.copytree(source, dest)
        else:
            if dest.is_dir() and not dest.is_symlink():
                shutil.rmtree(dest)
            shutil.copy2(source, dest)


def setup_claude_settings(
    worktree_path: Path,
    coral_dir: Path,
    *,
    research: bool = True,
    gateway_url: str | None = None,
    gateway_api_key: str | None = None,
    island_id: str | int | None = None,
) -> None:
    """Write Claude Code settings.json with permissions and gateway env."""
    from coral.hub._island import island_root

    claude_dir = worktree_path / ".claude"
    claude_dir.mkdir(exist_ok=True)

    private_dir = str(coral_dir.resolve() / "private")
    state_root_resolved = island_root(coral_dir, island_id).resolve()
    agents_dir = str(state_root_resolved / "agents")
    worktree_str = str(worktree_path.resolve())
    private_pattern = f"{private_dir}/**"
    agents_pattern = f"{agents_dir}/**"
    worktree_pattern = f"{worktree_str}/**"
    state_root_pattern = f"{state_root_resolved}/**"

    allow_rules: list[str] = [
        "Bash",
        f"Read(/{worktree_pattern})",
        f"Read(/{state_root_pattern})",
        f"Read(/{agents_pattern})",
        f"Edit(/{worktree_pattern})",
        f"Write(/{worktree_pattern})",
    ]
    if research:
        allow_rules.extend(["WebSearch", "WebFetch"])

    grader_source = grader_source_dir(coral_dir)
    if grader_source is not None:
        grader_pattern = f"{grader_source.resolve()}/**"
        allow_rules.append(f"Read(/{grader_pattern})")

    deny_rules: list[str] = [
        "Bash(git *)",
        f"Read(/{private_pattern})",
        "AskUserQuestion",
        "EnterPlanMode",
        "ExitPlanMode",
    ]
    if not research:
        deny_rules.extend(["WebSearch", "WebFetch"])

    permissions: dict = {
        "allow": allow_rules,
        "deny": deny_rules,
    }

    settings: dict = {
        "permissions": permissions,
    }

    if gateway_url or gateway_api_key:
        env: dict[str, str] = {}
        if gateway_url:
            env["ANTHROPIC_BASE_URL"] = gateway_url
        if gateway_api_key:
            env["ANTHROPIC_API_KEY"] = gateway_api_key
        env["ANTHROPIC_CUSTOM_HEADERS"] = ""
        settings["env"] = env

    settings_path = claude_dir / "settings.local.json"
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def setup_opencode_settings(
    worktree_path: Path,
    coral_dir: Path,
    *,
    research: bool = True,
    gateway_url: str | None = None,
    gateway_api_key: str | None = None,
    island_id: str | int | None = None,
) -> None:
    """Write OpenCode opencode.json with scoped permissions."""
    from coral.hub._island import island_root

    opencode_dir = worktree_path / ".opencode"
    opencode_dir.mkdir(exist_ok=True)

    private_pattern = str(coral_dir.resolve() / "private") + "/**"
    state_root_pattern = str(island_root(coral_dir, island_id).resolve()) + "/**"

    external_allow = {state_root_pattern: "allow"}
    grader_source = grader_source_dir(coral_dir)
    if grader_source is not None:
        external_allow[str(grader_source.resolve()) + "/**"] = "allow"

    settings: dict = {
        "$schema": "https://opencode.ai/config.json",
        "permission": {
            "*": "allow",
            "external_directory": external_allow,
            "read": {
                private_pattern: "deny",
            },
            "bash": {
                private_pattern: "deny",
            },
            "edit": {
                private_pattern: "deny",
            },
            "write": {
                private_pattern: "deny",
            },
            "question": "deny",
            "doom_loop": "allow",
            "webfetch": "deny" if not research else "allow",
            "websearch": "deny" if not research else "allow",
        },
    }

    if gateway_url:
        provider_options: dict[str, str] = {"baseURL": gateway_url}
        if gateway_api_key:
            provider_options["apiKey"] = gateway_api_key
        settings["provider"] = {
            "openai": {
                "npm": "@ai-sdk/openai",
                "name": "openai",
                "options": provider_options,
                "models": {
                    "gpt-5.4": {"name": "gpt-5.4"},
                    "claude-opus-4-6": {"name": "claude-opus-4-6"},
                },
            },
        }

    settings_path = opencode_dir / "opencode.json"
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def setup_codex_settings(
    worktree_path: Path,
    coral_dir: Path,
    *,
    research: bool = True,
    gateway_url: str | None = None,
    gateway_api_key: str | None = None,
    island_id: str | int | None = None,
) -> None:
    """Write Codex CLI config.toml with sandbox, approval, and web search settings."""
    codex_dir = worktree_path / ".codex"
    codex_dir.mkdir(exist_ok=True)

    web_search = "live" if research else "disabled"

    lines = [
        'model = "gpt-5.4"',
        'approval_policy = "never"',
        'sandbox_mode = "danger-full-access"',
        'personality = "pragmatic"',
        f'web_search = "{web_search}"',
    ]

    if gateway_url:
        lines += [
            'model_provider = "litellm"\n',
            "[model_providers.litellm]",
            'name = "LiteLLM Proxy"',
            f'base_url = "{gateway_url}/v1"',
            'wire_api = "responses"',
            'env_key = "OPENAI_API_KEY"',
        ]

    config_toml = "\n".join(lines) + "\n"

    settings_path = codex_dir / "config.toml"
    settings_path.write_text(config_toml, encoding="utf-8")


def setup_cursor_settings(
    worktree_path: Path,
    coral_dir: Path,
    *,
    research: bool = True,
    gateway_url: str | None = None,
    gateway_api_key: str | None = None,
    island_id: str | int | None = None,
) -> None:
    """Write .cursor/rules/coral.mdc with always-apply CORAL guardrails."""
    rules_dir = worktree_path / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)

    private_dir = str(coral_dir.resolve() / "private")

    body_lines = [
        "Always:",
        "",
        '- Use `coral eval -m "<short description>"` to stage, commit, and grade your work — never bare `git commit`.',
        "- Read the full task brief in `AGENTS.md` at the workspace root.",
        f"- Do not read or modify anything under `{private_dir}/` (grader internals, answer keys).",
        "- Share findings through `.cursor/notes/` and reusable tools through `.cursor/skills/` so other agents benefit.",
    ]
    if not research:
        body_lines.append("- Web search and web fetch are disabled for this run.")

    rules_md = (
        "---\n"
        "description: CORAL agent guardrails\n"
        "globs:\n"
        "alwaysApply: true\n"
        "---\n"
        "\n"
        "# CORAL Agent Guardrails\n"
        "\n" + "\n".join(body_lines) + "\n"
    )

    (rules_dir / "coral.mdc").write_text(rules_md, encoding="utf-8")


def setup_worktree_env(worktree_path: Path, setup_commands: list[str]) -> None:
    """Run setup commands and install coral in a worktree's venv."""
    if not setup_commands:
        return

    marker_file = worktree_path / ".coral_setup_complete"
    worktree_venv = worktree_path / ".venv"
    venv_python = resolve_venv_python(worktree_venv)

    if marker_file.exists() or venv_python.exists():
        logger.debug(f"Worktree environment already setup at {worktree_path}, skipping commands")
        return

    env_override = {"UV_PROJECT_ENVIRONMENT": str(worktree_venv)}
    run_setup_commands(setup_commands, worktree_path, extra_env=env_override)

    # Install coral into the worktree's venv so agents can use
    # ``uv run coral eval`` and graders can ``from coral.grader import ...``.
    venv_python = resolve_venv_python(worktree_venv)
    if venv_python.exists() and shutil.which("uv"):
        coral_root = Path(__file__).resolve().parent.parent.parent
        if (coral_root / "pyproject.toml").exists():
            logger.info(f"Installing coral into worktree venv from {coral_root}")
            env = _clean_env()
            env.update(env_override)
            result = subprocess.run(
                ["uv", "pip", "install", "--python", str(venv_python), "-e", str(coral_root)],
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                env=env,
            )
            if result.returncode != 0:
                logger.warning(f"Failed to install coral in worktree: {result.stderr.strip()}")

    marker_file.write_text("ok", encoding="utf-8")
