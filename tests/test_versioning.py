"""Regression tests for the hatch-vcs version contract."""

from __future__ import annotations

import re
import subprocess
from importlib.metadata import version as distribution_version
from pathlib import Path

import coral

ROOT = Path(__file__).resolve().parents[1]
GENERATED_VERSION_FILE = "coral/_version.py"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _release_tuple(version: str) -> tuple[int, int, int]:
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", version)
    if match is None:
        raise AssertionError(f"Expected a semantic version, got {version!r}")
    return tuple(int(part) for part in match.groups())


def test_runtime_version_comes_from_distribution_metadata():
    assert coral.__version__ == distribution_version("coral")


def test_generated_version_file_is_ignored_and_untracked():
    ignored = _git("check-ignore", "--quiet", GENERATED_VERSION_FILE)
    assert ignored.returncode == 0, "hatch-vcs output must stay ignored"

    tracked = _git("ls-files", "--", GENERATED_VERSION_FILE)
    assert tracked.returncode == 0
    assert tracked.stdout.strip() == "", "generated hatch-vcs output must not be committed"


def test_distribution_version_is_not_older_than_latest_reachable_tag():
    latest_tag = _git("describe", "--tags", "--abbrev=0", "--match", "v[0-9]*")
    assert latest_tag.returncode == 0, (
        "No reachable release tag; CI checkout must retain Git history and tags"
    )

    installed = distribution_version("coral")
    assert _release_tuple(installed) >= _release_tuple(latest_tag.stdout.strip()), (
        f"Installed version {installed} predates reachable tag {latest_tag.stdout.strip()}"
    )
