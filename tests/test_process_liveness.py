"""Tests for the cross-platform PID liveness probe."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from coral.cli._helpers import is_process_alive

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="exercises the POSIX os.kill branch"
)


def test_current_process_is_alive() -> None:
    assert is_process_alive(os.getpid())


def test_exited_process_is_not_alive() -> None:
    """A process that has exited is dead on both platforms.

    On Windows the kernel object outlives the process while a handle is still
    open, so this also covers the "handle exists" case that would otherwise be
    misreported as running.
    """
    process = subprocess.Popen([sys.executable, "-c", ""])
    process.wait()

    assert not is_process_alive(process.pid)


@pytest.mark.parametrize("pid", [0, -1, -12345])
def test_non_positive_pids_are_never_alive(pid: int) -> None:
    """``os.kill`` reads 0 and negatives as process groups, not processes.

    A truncated or corrupt ``manager.pid`` must not make the caller's own
    process group look like a running manager.
    """
    assert not is_process_alive(pid)


@posix_only
def test_invalid_parameter_oserror_is_reported_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows raises WinError 87 from ``os.kill`` instead of ProcessLookupError.

    Regression test for `coral status` crashing: the bare OSError escaped call
    sites that only caught ProcessLookupError.
    """

    def raise_invalid_parameter(pid: int, sig: int) -> None:
        raise OSError(22, "The parameter is incorrect", None, 87)

    monkeypatch.setattr(os, "kill", raise_invalid_parameter)

    assert not is_process_alive(4321)


@posix_only
def test_permission_error_means_alive(monkeypatch: pytest.MonkeyPatch) -> None:
    """A process owned by another user exists, so it counts as running."""

    def raise_permission_error(pid: int, sig: int) -> None:
        raise PermissionError("Operation not permitted")

    monkeypatch.setattr(os, "kill", raise_permission_error)

    assert is_process_alive(4321)


@posix_only
def test_process_lookup_error_means_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_lookup_error(pid: int, sig: int) -> None:
        raise ProcessLookupError("No such process")

    monkeypatch.setattr(os, "kill", raise_lookup_error)

    assert not is_process_alive(4321)
