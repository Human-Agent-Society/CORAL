"""Bubblewrap sandbox planning for local/WSL CORAL subprocesses."""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from coral.config import CoralConfig, GraderConfig
from coral.hub._island import island_root


class SandboxUnavailable(RuntimeError):  # noqa: N818
    """Raised when a required sandbox backend cannot be used."""


_FULL_ACCESS_RUNTIMES = {
    "claude_code",
    "codex",
    "cursor_agent",
    "kiro",
    "opencode",
    "pi",
}

_RUNTIME_ALIASES = {
    "claude": "claude_code",
    "claude-code": "claude_code",
    "openai": "codex",
    "openai-codex": "codex",
    "open-code": "opencode",
    "kiro-cli": "kiro",
    "cursor": "cursor_agent",
    "cursor-agent": "cursor_agent",
    "pi-agent": "pi",
    "pi_agent": "pi",
}

_BASE_ENV_KEYS = {
    "CI",
    "COLORTERM",
    "HOME",
    "LANG",
    "LC_ALL",
    "LOGNAME",
    "NO_PROXY",
    "PATH",
    "PYTHONIOENCODING",
    "REQUESTS_CA_BUNDLE",
    "SSL_CERT_FILE",
    "TERM",
    "TZ",
    "USER",
    "UV_PROJECT_ENVIRONMENT",
    "VIRTUAL_ENV",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
}

_SYSTEM_RO_BINDS = (
    "/bin",
    "/etc",
    "/lib",
    "/lib64",
    "/opt",
    "/usr",
)

_SYSTEM_SYMLINK_TARGET_FILES = (Path("/etc/resolv.conf"),)

_SUBMITTED_ENV_KEYS = {
    "CI",
    "COLORTERM",
    "LANG",
    "LC_ALL",
    "NO_PROXY",
    "PATH",
    "PYTHONIOENCODING",
    "REQUESTS_CA_BUNDLE",
    "SSL_CERT_FILE",
    "TERM",
    "TZ",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
}

_RUNTIME_HOME_FILE_ALLOWLIST = {
    ".claude": {
        ".credentials.json",
        "settings.json",
        "settings.local.json",
        "config.json",
        "config.toml",
    },
    ".codex": {"auth.json", "config.toml"},
    ".cursor": {"auth.json", "config.json", "settings.json"},
    ".kiro": {"auth.json", "config.json", "settings.json"},
    ".opencode": {"auth.json", "config.json", "opencode.json"},
    ".pi": {"auth.json", "config.json", "settings.json"},
}


@dataclass(frozen=True)
class AgentSandboxSpec:
    """Resolved bubblewrap view for one agent subprocess."""

    bwrap_path: str
    agent_id: str
    worktree_path: Path
    coral_dir: Path
    repo_dir: Path
    state_root: Path
    home_dir: Path
    shared_dir_name: str
    island_id: str | int | None = None
    runtime_home_source: Path | None = None
    coral_source_root: Path | None = None


@dataclass(frozen=True)
class SubmittedCodeSandboxSpec:
    """Resolved bubblewrap view for one grader-launched submitted-code subprocess."""

    bwrap_path: str
    codebase_path: Path
    eval_logs_dir: Path
    sandbox_codebase_path: str = "/workspace"
    sandbox_eval_logs_path: str = "/eval_logs"


def _runtime_is_full_access(runtime_name: str) -> bool:
    canonical = _RUNTIME_ALIASES.get(runtime_name, runtime_name)
    return canonical in _FULL_ACCESS_RUNTIMES


def _find_bwrap(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    return shutil.which("bwrap")


def resolve_agent_sandbox(
    config: CoralConfig,
    *,
    paths: Any,
    agent_id: str,
    runtime_name: str,
    shared_dir_name: str,
    island_id: str | int | None,
    bwrap_path: str | None = None,
    in_coral_docker: bool = False,
) -> AgentSandboxSpec | None:
    """Return the bwrap spec for an agent, or None when sandboxing is not needed."""

    # The Docker session already owns the hard boundary. Do not stack bwrap
    # inside it by default; Docker image support is handled separately.
    if in_coral_docker or config.run.session == "docker":
        return None

    sandbox = config.run.sandbox
    has_private = bool(config.grader.private)
    private_reason = "grader.private requires a private-safe sandbox"

    if sandbox.mode == "off":
        if has_private:
            raise SandboxUnavailable(f"{private_reason}; run.sandbox.mode=off is unsafe")
        return None

    if sandbox.backend == "none":
        if has_private or sandbox.mode == "required":
            reason = private_reason if has_private else "sandbox required"
            raise SandboxUnavailable(f"{reason}, but run.sandbox.backend=none")
        return None

    wants_bwrap = sandbox.backend in {"auto", "bwrap"}
    full_access_runtime = _runtime_is_full_access(runtime_name)
    should_enable = sandbox.mode == "required" or has_private or full_access_runtime

    if not should_enable:
        return None

    if not wants_bwrap:
        raise SandboxUnavailable(
            f"run.sandbox.backend={sandbox.backend!r} cannot satisfy local sandboxing"
        )

    resolved_bwrap = _find_bwrap(bwrap_path)
    if not resolved_bwrap:
        if not has_private and sandbox.mode == "auto" and sandbox.backend == "auto":
            return None
        reason = private_reason if has_private else "sandbox required"
        raise SandboxUnavailable(
            f"{reason}, but bubblewrap (bwrap) is not installed or not on PATH. "
            "Install bubblewrap or use run.session=docker."
        )

    worktree_path = paths.agents_dir / agent_id
    home_dir = paths.coral_dir / "agent_homes" / agent_id / "home"
    runtime_home_source = Path.home() / shared_dir_name
    return AgentSandboxSpec(
        bwrap_path=resolved_bwrap,
        agent_id=agent_id,
        worktree_path=worktree_path,
        coral_dir=paths.coral_dir,
        repo_dir=paths.repo_dir,
        state_root=island_root(paths.coral_dir, island_id),
        home_dir=home_dir,
        shared_dir_name=shared_dir_name,
        island_id=island_id,
        runtime_home_source=runtime_home_source if runtime_home_source.is_dir() else None,
        coral_source_root=_coral_source_root(),
    )


def resolve_submitted_code_sandbox(
    config: GraderConfig,
    *,
    codebase_path: str | Path,
    private_dir: str | Path,
    eval_logs_dir: str | Path,
    bwrap_path: str | None = None,
) -> SubmittedCodeSandboxSpec | None:
    """Return a bwrap spec for grader-launched submitted code.

    The trusted grader process may read ``private_dir``. Any child process that
    executes agent-submitted code should receive a narrower view, especially
    when ``grader.private`` declares hidden fixtures or answer material.
    """

    sandbox = config.sandbox
    has_private = bool(config.private)
    private_reason = "grader.private requires a submitted code sandbox"

    if sandbox.mode == "off":
        if has_private:
            raise SandboxUnavailable(f"{private_reason}; grader.sandbox.mode=off is unsafe")
        return None

    if sandbox.backend == "none":
        if has_private or sandbox.mode == "required":
            raise SandboxUnavailable(
                f"{private_reason if has_private else 'submitted code sandbox required'}, "
                "but grader.sandbox.backend=none"
            )
        return None

    if sandbox.backend not in {"auto", "bwrap"}:
        raise SandboxUnavailable(
            f"grader.sandbox.backend={sandbox.backend!r} cannot sandbox submitted code"
        )

    resolved_bwrap = _find_bwrap(bwrap_path)
    should_enable = (
        sandbox.mode == "required"
        or has_private
        or sandbox.backend == "bwrap"
        or resolved_bwrap is not None
    )
    if not should_enable:
        return None

    if not resolved_bwrap:
        reason = private_reason if has_private else "submitted code sandbox required"
        raise SandboxUnavailable(
            f"{reason}, but bubblewrap (bwrap) is not installed or not on PATH. "
            "Install bubblewrap or set grader.sandbox.mode=off only for non-private tasks."
        )

    return SubmittedCodeSandboxSpec(
        bwrap_path=resolved_bwrap,
        codebase_path=Path(codebase_path).resolve(),
        eval_logs_dir=Path(eval_logs_dir).resolve(),
    )


def sanitize_agent_env(
    env: dict[str, str],
    *,
    extra_allowed_keys: Iterable[str] = (),
) -> dict[str, str]:
    """Filter host env before launching a private-safe agent sandbox."""

    allowed = set(_BASE_ENV_KEYS)
    allowed.update(extra_allowed_keys)
    return {key: val for key, val in env.items() if key in allowed}


def sanitize_submitted_code_env(env: dict[str, str]) -> dict[str, str]:
    """Filter grader env before launching untrusted submitted code."""

    filtered = {key: val for key, val in env.items() if key in _SUBMITTED_ENV_KEYS}
    filtered["HOME"] = "/tmp"
    filtered["USER"] = "sandbox"
    filtered["LOGNAME"] = "sandbox"
    return filtered


def build_agent_bwrap_command(cmd: list[str], spec: AgentSandboxSpec) -> list[str]:
    """Wrap an agent command in a bubblewrap mount namespace."""

    spec.home_dir.mkdir(parents=True, exist_ok=True)
    _provision_runtime_home_state(spec)
    executable_binds = _runtime_executable_binds(cmd)
    system_file_binds = _system_symlink_target_binds()
    coral_source_root = _usable_coral_source_root(spec.coral_source_root)
    bwrap_cmd: list[str] = [
        spec.bwrap_path,
        "--die-with-parent",
        "--new-session",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
    ]

    system_binds = [Path(path) for path in _SYSTEM_RO_BINDS if Path(path).exists()]
    _add_destination_dirs(
        bwrap_cmd,
        [
            *system_binds,
            spec.coral_dir,
            spec.worktree_path,
            spec.repo_dir,
            spec.state_root,
            spec.home_dir,
            *(dest.parent for _, dest in executable_binds),
            *(dest.parent for _, dest in system_file_binds),
            *(path for path in (coral_source_root,) if path is not None),
        ],
    )

    for path in system_binds:
        if path.exists():
            bwrap_cmd.extend(["--ro-bind", str(path), str(path)])

    for source, dest in system_file_binds:
        bwrap_cmd.extend(["--ro-bind", str(source), str(dest)])

    if coral_source_root is not None:
        bwrap_cmd.extend(["--ro-bind", str(coral_source_root), str(coral_source_root)])

    for source, dest in executable_binds:
        bwrap_cmd.extend(["--ro-bind", str(source), str(dest)])

    for path in _safe_coral_metadata(spec.coral_dir):
        if path.exists():
            bwrap_cmd.extend(["--ro-bind", str(path), str(path)])

    for path in (spec.worktree_path, spec.repo_dir, spec.state_root, spec.home_dir):
        bwrap_cmd.extend(["--bind", str(path), str(path)])

    bwrap_cmd.extend(
        [
            "--setenv",
            "HOME",
            str(spec.home_dir),
            "--setenv",
            "USER",
            "agent",
            "--setenv",
            "LOGNAME",
            "agent",
            "--chdir",
            str(spec.worktree_path),
            "--",
            *cmd,
        ]
    )
    return bwrap_cmd


def build_submitted_code_bwrap_command(
    cmd: list[str],
    spec: SubmittedCodeSandboxSpec,
) -> list[str]:
    """Wrap a grader-launched submitted-code command in a reduced filesystem view."""

    spec.eval_logs_dir.mkdir(parents=True, exist_ok=True)
    mapped_cmd = [_map_submitted_arg(arg, spec) for arg in cmd]
    bwrap_cmd: list[str] = [
        spec.bwrap_path,
        "--die-with-parent",
        "--new-session",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
    ]

    system_binds = [Path(path) for path in _SYSTEM_RO_BINDS if Path(path).exists()]
    system_file_binds = _system_symlink_target_binds()
    executable_binds = _runtime_executable_binds(mapped_cmd)
    _add_destination_dirs(
        bwrap_cmd,
        [
            *system_binds,
            *(dest.parent for _, dest in system_file_binds),
            *(dest.parent for _, dest in executable_binds),
            Path(spec.sandbox_codebase_path),
            Path(spec.sandbox_eval_logs_path),
        ],
    )

    for path in system_binds:
        if path.exists():
            bwrap_cmd.extend(["--ro-bind", str(path), str(path)])

    for source, dest in system_file_binds:
        bwrap_cmd.extend(["--ro-bind", str(source), str(dest)])

    for source, dest in executable_binds:
        bwrap_cmd.extend(["--ro-bind", str(source), str(dest)])

    bwrap_cmd.extend(
        [
            "--bind",
            str(spec.codebase_path),
            spec.sandbox_codebase_path,
            "--bind",
            str(spec.eval_logs_dir),
            spec.sandbox_eval_logs_path,
            "--setenv",
            "HOME",
            "/tmp",
            "--setenv",
            "USER",
            "sandbox",
            "--setenv",
            "LOGNAME",
            "sandbox",
            "--chdir",
            spec.sandbox_codebase_path,
            "--",
            *mapped_cmd,
        ]
    )
    return bwrap_cmd


def _safe_coral_metadata(coral_dir: Path) -> tuple[Path, ...]:
    return (
        coral_dir / "config.yaml",
        coral_dir / "config_dir",
    )


def _coral_source_root() -> Path | None:
    root = Path(__file__).resolve().parents[2]
    return _usable_coral_source_root(root)


def _usable_coral_source_root(root: Path | None) -> Path | None:
    if root is None:
        return None
    if (root / "pyproject.toml").is_file() and (root / "coral").is_dir():
        return root
    return None


def _provision_runtime_home_state(spec: AgentSandboxSpec) -> None:
    """Copy bounded runtime auth/config state into the sandbox HOME.

    The agent must authenticate its runtime CLI, but the sandbox should not bind
    the operator's real home directory. Copy only top-level files (for Codex,
    this covers auth.json/config.toml) and let the agent create its own caches
    and session logs under the per-run HOME.
    """

    source = spec.runtime_home_source
    if source is None or not source.is_dir():
        return

    dest = spec.home_dir / spec.shared_dir_name
    dest.mkdir(parents=True, exist_ok=True)
    allowed_files = _RUNTIME_HOME_FILE_ALLOWLIST.get(spec.shared_dir_name, set())
    try:
        for item in source.iterdir():
            if item.name not in allowed_files:
                continue
            if not item.is_file() and not item.is_symlink():
                continue
            target = dest / item.name
            if target.exists():
                continue
            shutil.copy2(item, target, follow_symlinks=True)
    except OSError as e:
        raise SandboxUnavailable(
            f"failed to provision runtime state from {source} into {dest}: {e}"
        ) from e


def _runtime_executable_binds(cmd: list[str]) -> tuple[tuple[Path, Path], ...]:
    if not cmd:
        return ()

    executable = Path(cmd[0])
    if executable.is_absolute():
        dest = executable
    else:
        found = shutil.which(cmd[0])
        if not found:
            return ()
        dest = Path(found)

    try:
        source = dest.resolve(strict=True)
    except OSError:
        return ()

    if not source.is_file() or _is_under_system_bind(dest):
        return ()
    return ((source, dest),)


def _system_symlink_target_binds() -> tuple[tuple[Path, Path], ...]:
    binds: list[tuple[Path, Path]] = []
    for path in _SYSTEM_SYMLINK_TARGET_FILES:
        try:
            target = path.resolve(strict=True)
        except OSError:
            continue
        if _is_under_system_bind(target):
            continue
        binds.append((target, target))
    return tuple(binds)


def _is_under_system_bind(path: Path) -> bool:
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        resolved = path
    for root in _SYSTEM_RO_BINDS:
        try:
            resolved.relative_to(Path(root))
            return True
        except ValueError:
            continue
    return False


def _add_destination_dirs(cmd: list[str], paths: Iterable[Path]) -> None:
    seen: set[str] = set()
    for path in paths:
        if not path.is_absolute():
            continue
        current = Path("/")
        for part in path.parts[1:]:
            current /= part
            rendered = str(current)
            if rendered not in seen:
                cmd.extend(["--dir", rendered])
                seen.add(rendered)


def _map_submitted_arg(arg: str, spec: SubmittedCodeSandboxSpec) -> str:
    mapped = _map_path_arg(arg, spec.codebase_path, spec.sandbox_codebase_path)
    if mapped is not None:
        return mapped
    mapped = _map_path_arg(arg, spec.eval_logs_dir, spec.sandbox_eval_logs_path)
    if mapped is not None:
        return mapped
    return arg


def _map_path_arg(arg: str, source_root: Path, sandbox_root: str) -> str | None:
    path = Path(arg)
    if not path.is_absolute():
        return None
    try:
        rel = path.resolve().relative_to(source_root)
    except (OSError, ValueError):
        return None
    if str(rel) == ".":
        return sandbox_root
    return str(PurePosixPath(sandbox_root, *rel.parts))
