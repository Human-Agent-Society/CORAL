"""Integration tests for tagging the source of a dev-to-main promotion."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG_SCRIPT = ROOT / ".github" / "scripts" / "tag-promoted-release.sh"


def _run(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def _git(cwd: Path, *args: str) -> str:
    return _run(cwd, "git", *args).stdout.strip()


def _commit(repo: Path, content: str, message: str) -> str:
    (repo / "payload.txt").write_text(content, encoding="utf-8")
    _git(repo, "add", "payload.txt")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _new_repo(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    _run(tmp_path, "git", "init", "--bare", str(remote))
    _run(tmp_path, "git", "init", "--initial-branch=main", str(repo))
    _git(repo, "config", "user.name", "Release Test")
    _git(repo, "config", "user.email", "release-test@example.com")
    _commit(repo, "base\n", "base")
    _git(repo, "branch", "dev")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", "main", "dev")
    return repo, remote


def _promote(repo: Path, content: str) -> tuple[str, str]:
    _git(repo, "checkout", "dev")
    source_sha = _commit(repo, content, "dev change")
    _git(repo, "push", "origin", "dev")
    _git(repo, "checkout", "main")
    _git(repo, "merge", "--no-ff", "dev", "-m", "promote dev")
    promoted_sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "push", "origin", "main")
    return source_sha, promoted_sha


def _tag_release(
    repo: Path,
    tmp_path: Path,
    source_sha: str,
    promoted_sha: str,
) -> tuple[subprocess.CompletedProcess[str], str]:
    output = tmp_path / "github-output"
    env = os.environ.copy()
    env.update(
        {
            "BUMP": "patch",
            "FORCE": "false",
            "GITHUB_OUTPUT": str(output),
            "SOURCE_REF": source_sha,
            "PROMOTED_REF": promoted_sha,
        }
    )
    result = subprocess.run(
        ["bash", str(TAG_SCRIPT)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    github_output = output.read_text(encoding="utf-8") if output.exists() else ""
    return result, github_output


def test_release_tag_points_to_promoted_dev_commit(tmp_path: Path):
    repo, remote = _new_repo(tmp_path)
    _git(repo, "tag", "-a", "v1.2.3", "-m", "Release v1.2.3")
    _git(repo, "push", "origin", "v1.2.3")
    source_sha, promoted_sha = _promote(repo, "release payload\n")

    result, github_output = _tag_release(repo, tmp_path, source_sha, promoted_sha)

    assert result.returncode == 0, result.stderr
    assert _git(repo, "rev-parse", "v1.2.4^{commit}") == source_sha
    assert _git(remote, "rev-parse", "v1.2.4^{commit}") == source_sha
    assert "tagged=true" in github_output
    assert "version=v1.2.4" in github_output


def test_release_rejects_promotion_with_a_different_main_tree(tmp_path: Path):
    repo, _remote = _new_repo(tmp_path)
    _git(repo, "tag", "-a", "v1.2.3", "-m", "Release v1.2.3")
    _git(repo, "push", "origin", "v1.2.3")
    source_sha, _promoted_sha = _promote(repo, "release payload\n")
    promoted_sha = _commit(repo, "main-only payload\n", "main-only change")
    _git(repo, "push", "origin", "main")

    result, _github_output = _tag_release(repo, tmp_path, source_sha, promoted_sha)

    assert result.returncode != 0
    assert "promoted dev tree differs" in result.stdout
    assert _git(repo, "tag", "--list", "v1.2.4") == ""


def test_release_repairs_a_legacy_main_only_tag(tmp_path: Path):
    repo, _remote = _new_repo(tmp_path)
    _source_sha, first_promotion = _promote(repo, "first release\n")
    _git(repo, "tag", "-a", "v1.2.3", first_promotion, "-m", "Release v1.2.3")
    _git(repo, "push", "origin", "v1.2.3")
    source_sha, promoted_sha = _promote(repo, "second release\n")

    result, _github_output = _tag_release(repo, tmp_path, source_sha, promoted_sha)

    assert result.returncode == 0, result.stderr
    assert "repairs the legacy divergence" in result.stdout
    assert _git(repo, "rev-parse", "v1.2.4^{commit}") == source_sha
    assert _run(repo, "git", "merge-base", "--is-ancestor", "v1.2.4", "dev").returncode == 0
