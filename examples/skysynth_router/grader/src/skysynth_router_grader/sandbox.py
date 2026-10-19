"""Spawn the candidate worker behind a deny-default OS boundary.

macOS: ``/usr/bin/sandbox-exec`` with a Seatbelt profile that denies
everything, then allows back exactly the interpreter tree, the staged
candidate directory, and the system libraries a Python process needs to
start. No network. No home directory. No run directory. Credentials are not
inherited because the environment is rebuilt from scratch.

This is task-specific on purpose. Anthropic's ``sandbox-runtime`` (CORAL's
``agents.sandbox`` provider) is not installed on this machine, and building a
general provider was out of scope; what matters is that the boundary is
enforced by the kernel and verified by a test, not assumed from a directory
name. On a host without ``sandbox-exec`` the grader refuses to run rather
than silently evaluating unsandboxed -- see ``ensure_supported``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

SANDBOX_EXEC = "/usr/bin/sandbox-exec"

#: System paths a Python interpreter needs readable to start on macOS. None
#: of them can hold study data.
_SYSTEM_READS = (
    "/usr/lib",
    "/usr/share",
    "/System/Library",
    "/private/var/db/timezone",
    "/Library/Preferences/Logging",
)
_DEVICE_READS = ("/dev/null", "/dev/urandom", "/dev/random", "/dev/tty")
#: Path components that must be traversable for absolute paths to resolve.
_TRAVERSE = ("/", "/Users", "/private", "/private/var", "/private/var/folders")


def interpreter_roots() -> list[Path]:
    """The interpreter's own trees: its venv (if any) and base install.

    The worker runs under the grader venv's interpreter in isolated mode, so
    it can import PyYAML (task.md permits it) and nothing from the user site.
    """
    roots = {Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()}
    exe = Path(sys.executable).resolve()
    roots.add(exe.parent.parent)
    return sorted(roots)


def ensure_supported() -> None:
    if sys.platform != "darwin":
        raise RuntimeError(
            "the candidate sandbox is implemented with macOS sandbox-exec; "
            "this host cannot enforce the boundary, refusing to evaluate"
        )
    if not os.access(SANDBOX_EXEC, os.X_OK):
        raise RuntimeError(f"{SANDBOX_EXEC} is not executable; refusing to evaluate unsandboxed")


def _sb(path: Path | str) -> str:
    return str(path).replace("\\", "\\\\").replace('"', '\\"')


def build_profile(stage_dir: Path) -> str:
    """Seatbelt profile: deny by default, allow the minimum back."""
    stage = stage_dir.resolve()
    reads = [f'(subpath "{_sb(r)}")' for r in interpreter_roots()]
    reads.append(f'(subpath "{_sb(stage)}")')
    reads += [f'(subpath "{_sb(p)}")' for p in _SYSTEM_READS]
    reads += [f'(literal "{_sb(p)}")' for p in _DEVICE_READS]
    reads += [f'(literal "{_sb(p)}")' for p in _TRAVERSE]
    # every ancestor of the stage dir and interpreter must be traversable
    for root in [stage, *interpreter_roots()]:
        for anc in root.parents:
            reads.append(f'(literal "{_sb(anc)}")')
    execs = [f'(subpath "{_sb(r)}")' for r in interpreter_roots()]
    writes = [
        f'(subpath "{_sb(stage)}")',
        '(literal "/dev/null")',
        '(literal "/dev/stdout")',
        '(literal "/dev/stderr")',
        '(literal "/dev/tty")',
    ]
    lines = [
        "(version 1)",
        "(deny default)",
        "(allow process-fork)",
        "(allow process-exec " + " ".join(sorted(set(execs))) + ")",
        "(allow file-read* " + " ".join(sorted(set(reads))) + ")",
        "(allow file-read-metadata)",
        "(allow file-write* " + " ".join(writes) + ")",
        "(allow sysctl-read)",
        "(deny network*)",
    ]
    return "\n".join(lines) + "\n"


def worker_command(stage_dir: Path, profile_path: Path) -> list[str]:
    worker = Path(__file__).with_name("worker.py")
    # The worker is copied into the stage so the sandbox needs no read
    # allowance on the grader package directory.
    staged_worker = stage_dir / "_router_worker.py"
    if not staged_worker.exists():
        shutil.copy2(worker, staged_worker)
    return [SANDBOX_EXEC, "-f", str(profile_path), sys.executable, "-I", "-u", str(staged_worker)]


def clean_env(stage_dir: Path) -> dict[str, str]:
    """Rebuilt from nothing: no inherited API keys, tokens, or proxies."""
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(stage_dir),
        "TMPDIR": str(stage_dir),
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "LANG": "C.UTF-8",
    }


def spawn(stage_dir: Path) -> subprocess.Popen[str]:
    ensure_supported()
    stage_dir = stage_dir.resolve()
    profile_path = stage_dir / "_sandbox.sb"
    profile_path.write_text(build_profile(stage_dir))
    return subprocess.Popen(
        worker_command(stage_dir, profile_path),
        cwd=str(stage_dir),
        env=clean_env(stage_dir),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
