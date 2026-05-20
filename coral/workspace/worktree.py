"""Per-agent git worktree creation, shared state, and permissions."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

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


def setup_gitignore(worktree_path: Path) -> None:
    """Write .gitignore to exclude CORAL-managed files from git."""
    gitignore_path = worktree_path / ".gitignore"
    entries = {
        ".coral_agent_id",
        ".coral_dir",
        "CLAUDE.md",
        "AGENTS.md",
        ".claude/",
        ".codex/",
        ".cursor/",
        ".opencode/",
        ".pi/",
        ".venv/",
    }

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


def get_coral_dir(worktree_path: Path) -> Path | None:
    """Read the shared .coral directory path from the .coral_dir breadcrumb file."""
    ref_file = worktree_path / ".coral_dir"
    if ref_file.exists():
        return Path(ref_file.read_text().strip())
    return None


def setup_shared_state(
    worktree_path: Path, coral_dir: Path, shared_dir_name: str = ".claude"
) -> None:
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
        "agents",
        "attempts",
        "logs",
        "heartbeat",
        # Per-agent role descriptions. Each agent owns and edits its own
        # roles/<agent_id>.md; everyone reads everyone else's. Must be
        # a symlink to public/ so per-agent writes via .claude/roles/
        # land in shared state rather than getting siloed in the worktree.
        "roles",
        # Per-attempt eval artifacts (subprocess logs, terminal recordings,
        # verifier output, etc.) that the grader writes via TaskGrader.eval_logs_dir.
        # Lives outside the grader checkout so it survives daemon cleanup.
        "eval_logs",
    ]
    for item in shared_items:
        src = coral_public / item
        dst = shared_dir / item
        # Self-healing: if a previous (buggy) run wrote into a real local
        # directory at this path instead of a symlink, migrate any files
        # into the shared dir, then replace the local dir with a symlink.
        # Only triggers when src/dst would have collided — for new worktrees
        # the symlink branch below runs first.
        if dst.exists() and not dst.is_symlink() and dst.is_dir():
            src.mkdir(parents=True, exist_ok=True)
            for entry in dst.iterdir():
                target = src / entry.name
                if not target.exists():
                    shutil.move(str(entry), str(target))
            try:
                dst.rmdir()
            except OSError:
                # Directory still has unmoved entries (collisions). Leave it
                # in place and skip the symlink so we don't lose data.
                continue
        if not dst.exists() and not dst.is_symlink():
            try:
                rel = os.path.relpath(src.resolve(), shared_dir.resolve())
                dst.symlink_to(rel)
            except (ValueError, OSError):
                dst.symlink_to(src.resolve())


def apply_runtime_mounts(
    worktree_path: Path,
    mounts: dict[str, str],
    base_dir: Path,
) -> None:
    """Copy host files into the agent worktree per ``runtime_options.mounts``.

    ``mounts`` is a ``{source: dest}`` dict (matching ``docker -v`` source-first
    convention):

    - **source** is a host path with ``~`` expansion. Resolved relative to
      ``base_dir`` (typically the task directory) when not absolute.
    - **dest** is worktree-relative (e.g. ``.claude/settings.json``). Must
      stay inside the worktree — ``..`` and absolute paths are rejected.

    Files are copied (not symlinked) on every agent setup, so edits to the
    source propagate at the next agent restart but the worktree owns its own
    snapshot in between. Parent dirs are created. Existing dest files are
    overwritten — the call is the last hook before the agent starts, so
    user-supplied files win over CORAL's defaults (notably, mounting to
    ``.claude/settings.local.json`` will replace what
    ``setup_claude_settings`` just wrote).

    For Claude Code settings the recommended dest is ``.claude/settings.json``
    (no ``.local`` suffix). Claude Code natively merges that with CORAL's
    ``settings.local.json``, so the user's MCP servers / hooks / env layer
    on top of CORAL's required worktree-scoped permissions without anyone
    having to hand-merge JSON.

    Raises:
        FileNotFoundError: if ``source`` does not resolve to an existing path.
        ValueError: if ``dest`` escapes ``worktree_path``.
    """
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
) -> None:
    """Write Claude Code settings.json with permissions and gateway env.

    Grants the agent all tool permissions via allow rules (replacing
    --dangerously-skip-permissions).  When a gateway is configured, sets
    ANTHROPIC_BASE_URL and ANTHROPIC_API_KEY in the settings ``env`` so
    they override the user's global ``~/.claude/settings.json``.
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
        # Tools that block on human approval — there is no human in the
        # loop in CORAL. Leaving them enabled causes the agent to stall
        # indefinitely waiting for a reply that never comes. Planning
        # belongs in TodoWrite / focus notes; uncertainty belongs in an
        # eval message, not a question.
        "AskUserQuestion",
        "EnterPlanMode",
        "ExitPlanMode",
    ]
    if not research:
        deny_rules.extend(["WebSearch", "WebFetch"])

    permissions: dict = {
        "defaultMode": "auto",
        "allow": allow_rules,
        "deny": deny_rules,
    }

    settings: dict = {
        "permissions": permissions,
    }

    # Route agent traffic through gateway by overriding env in settings.
    # Claude Code reads env vars from settings, not the OS environment,
    # so process-level env vars have no effect.
    if gateway_url or gateway_api_key:
        env: dict[str, str] = {}
        if gateway_url:
            env["ANTHROPIC_BASE_URL"] = gateway_url
        if gateway_api_key:
            env["ANTHROPIC_API_KEY"] = gateway_api_key
        # Clear custom headers so the agent doesn't send them to the
        # local gateway — LiteLLM handles upstream headers via its own
        # config.  Without this, headers from the user's global settings
        env["ANTHROPIC_CUSTOM_HEADERS"] = ""
        settings["env"] = env

    settings_path = claude_dir / "settings.local.json"
    # Always overwrite — each agent needs its own copy
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")


def setup_opencode_settings(
    worktree_path: Path,
    coral_dir: Path,
    *,
    research: bool = True,
    gateway_url: str | None = None,
    gateway_api_key: str | None = None,
) -> None:
    """Write OpenCode opencode.json with scoped permissions.

    Allows access to the agent's worktree and shared public state,
    but denies access to .coral/private/ (grader data, answer keys).
    When a gateway is configured, patches the provider's baseURL so
    agent traffic routes through the LiteLLM proxy.
    """
    opencode_dir = worktree_path / ".opencode"
    opencode_dir.mkdir(exist_ok=True)

    private_pattern = str(coral_dir.resolve() / "private") + "/**"
    public_pattern = str(coral_dir.resolve() / "public") + "/**"

    settings: dict = {
        "$schema": "https://opencode.ai/config.json",
        "permission": {
            "*": "allow",
            "external_directory": {
                public_pattern: "allow",
            },
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
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")


def setup_codex_settings(
    worktree_path: Path,
    coral_dir: Path,
    *,
    research: bool = True,
    gateway_url: str | None = None,
    gateway_api_key: str | None = None,
) -> None:
    """Write Codex CLI config.toml with sandbox, approval, and web search settings.

    Sets the agent to full-auto mode (no approval prompts, workspace-write
    sandbox) and toggles web_search based on the *research* flag.  When a
    gateway is configured, sets ``base_url`` so the agent routes
    traffic through the LiteLLM proxy.
    """
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
    settings_path.write_text(config_toml)


def setup_cursor_settings(
    worktree_path: Path,
    coral_dir: Path,
    *,
    research: bool = True,
    # Cursor Agent uses its own auth (`cursor-agent login`) and does not
    # honour the OpenAI/Anthropic base-url env vars LiteLLM relies on.
    # The kwargs are accepted so the manager dispatch can stay uniform.
    gateway_url: str | None = None,  # noqa: ARG001
    gateway_api_key: str | None = None,  # noqa: ARG001
) -> None:
    """Write `.cursor/rules/coral.mdc` with always-apply CORAL guardrails.

    Cursor Agent reads `.cursor/rules/*.mdc` files via its native rules
    system in addition to AGENTS.md. The full task brief lives in AGENTS.md;
    this file holds short, high-priority constraints that should survive
    context pressure (eval workflow, private-dir guard, sharing channels).

    Permission bypass is handled at the CLI via `--force`, not in a settings
    file — so unlike claude/opencode/codex there is no permissions block.
    """
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

    (rules_dir / "coral.mdc").write_text(rules_md)


def setup_worktree_env(worktree_path: Path, setup_commands: list[str]) -> None:
    """Run setup commands and install coral in a worktree's venv.

    After creating a worktree, we need to:
    1. Run workspace setup commands (e.g. ``uv sync``) so the worktree
       gets its own ``.venv`` with task dependencies.
    2. Install ``coral`` into that venv so ``coral eval`` is available
       when the agent uses ``uv run``.

    Each worktree gets its own isolated ``.venv`` via UV_PROJECT_ENVIRONMENT
    to prevent concurrent agents from corrupting a shared venv.

    Idempotent: if the worktree's ``.venv`` is already populated (the python
    binary exists), skip both the setup commands and the coral reinstall.
    Deps don't change mid-run, so re-running ``uv sync`` on every
    interrupt-and-resume cycle is wasted work. To force a re-sync, delete the
    ``.venv`` directory before resuming.
    """
    if not setup_commands:
        return

    # Force uv to create/use a venv inside this worktree, even if
    # pyproject.toml is resolved from a parent directory.
    worktree_venv = worktree_path / ".venv"
    venv_python = worktree_venv / "bin" / "python"
    if venv_python.exists():
        logger.debug(f"Worktree venv already populated at {worktree_venv}, skipping setup commands")
        return

    env_override = {"UV_PROJECT_ENVIRONMENT": str(worktree_venv)}
    run_setup_commands(setup_commands, worktree_path, extra_env=env_override)

    # Install coral into the worktree's venv so agents can use
    # ``uv run coral eval`` and graders can ``from coral.grader import ...``.
    venv_python = worktree_venv / "bin" / "python"
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
