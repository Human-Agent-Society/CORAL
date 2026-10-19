"""Capability probes for the SkySynth router tests.

The candidate boundary is macOS ``sandbox-exec`` (Seatbelt). Being on macOS is
not enough: managed or hardened hosts ship the binary but refuse to apply a
profile, and a test that assumes otherwise hangs on the worker's timeouts
instead of failing fast. So the tests skip on a real probe: a deny-default
profile must actually run a trivial command, quickly, and the deny must bite.
"""

from __future__ import annotations

import functools
import os
import subprocess
import sys
from pathlib import Path

import pytest

SANDBOX_EXEC = "/usr/bin/sandbox-exec"


@functools.lru_cache(maxsize=1)
def sandbox_unavailable_reason() -> str | None:
    """None when Seatbelt works here; otherwise a one-line reason to skip on."""
    if os.environ.get("SKYSYNTH_ASSUME_NO_SANDBOX"):
        return "SKYSYNTH_ASSUME_NO_SANDBOX is set (CI parity check)"
    if sys.platform != "darwin":
        return "candidate sandbox uses macOS sandbox-exec"
    if not Path(SANDBOX_EXEC).is_file():
        return f"{SANDBOX_EXEC} is missing"
    allow = "(version 1)(allow default)"
    deny_read = '(version 1)(allow default)(deny file-read* (subpath "/etc"))'
    try:
        ok = subprocess.run(
            [SANDBOX_EXEC, "-p", allow, "/usr/bin/true"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if ok.returncode != 0:
            return f"sandbox-exec cannot apply a profile here: {ok.stderr.strip()[:120] or ok.returncode}"
        denied = subprocess.run(
            [SANDBOX_EXEC, "-p", deny_read, "/bin/cat", "/etc/hosts"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if denied.returncode == 0:
            return "sandbox-exec ran but did not enforce a deny rule"
    except (OSError, subprocess.SubprocessError) as exc:
        return f"sandbox-exec probe failed: {type(exc).__name__}: {exc}"
    return None


needs_sandbox = pytest.mark.skipif(
    sandbox_unavailable_reason() is not None,
    reason=f"skipped: {sandbox_unavailable_reason()}",
)
