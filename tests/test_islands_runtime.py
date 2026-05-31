"""Integration tests for Phase 2 — multi-island runtime activation."""

from __future__ import annotations

from pathlib import Path

from coral.config import CoralConfig
from coral.workspace.project import create_project
from coral.workspace.worktree import setup_shared_state


def _base_config_dict(repo: Path) -> dict:
    return {
        "task": {"name": "t", "description": "d"},
        "workspace": {
            "results_dir": str(repo / "results"),
            "repo_path": str(repo / "src"),
        },
    }


def test_create_project_single_island_keeps_legacy_layout(tmp_path):
    """When islands.count == 1, no islands/ subdir is created."""
    repo = tmp_path / "myrepo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "README.md").write_text("hi")

    cfg = CoralConfig.from_dict(_base_config_dict(repo))
    assert cfg.islands.count == 1
    paths = create_project(cfg, config_dir=repo)

    assert paths.coral_dir.is_dir()
    assert (paths.coral_dir / "public").is_dir()
    assert (paths.coral_dir / "public" / "attempts").is_dir()
    assert (paths.coral_dir / "public" / "skills").is_dir()
    # No multi-island subtree
    assert not (paths.coral_dir / "islands").exists()


def test_create_project_multi_island_creates_per_island_subtrees(tmp_path):
    """When islands.count > 1, each island gets its own subtree."""
    repo = tmp_path / "myrepo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "README.md").write_text("hi")

    data = _base_config_dict(repo)
    data["islands"] = {"count": 3}
    cfg = CoralConfig.from_dict(data)
    paths = create_project(cfg, config_dir=repo)

    islands_root = paths.coral_dir / "islands"
    assert islands_root.is_dir()
    for i in range(3):
        island = islands_root / str(i)
        for sub in ("attempts", "notes", "skills", "agents", "roles", "heartbeat", "eval_logs", "logs"):
            assert (island / sub).is_dir(), f"missing {island / sub}"


def test_create_project_multi_island_seeds_bundled_skills_per_island(tmp_path):
    """Bundled framework skills (deep-research, librarian, …) are seeded into every island."""
    repo = tmp_path / "myrepo"
    (repo / "src").mkdir(parents=True)

    data = _base_config_dict(repo)
    data["islands"] = {"count": 2}
    cfg = CoralConfig.from_dict(data)
    paths = create_project(cfg, config_dir=repo)

    for i in range(2):
        sk = paths.coral_dir / "islands" / str(i) / "skills"
        # At least one bundled skill must land on each island
        bundled = list(sk.iterdir())
        assert bundled, f"island {i} got no bundled skills"
        names = {p.name for p in bundled}
        assert "deep-research" in names or "skill-creator" in names, (
            f"island {i} bundled skills look wrong: {names}"
        )


def test_create_project_multi_island_per_island_eval_counter_files(tmp_path):
    """Per-island eval_count files are absent on creation (lazy bump)."""
    repo = tmp_path / "myrepo"
    (repo / "src").mkdir(parents=True)

    data = _base_config_dict(repo)
    data["islands"] = {"count": 2}
    cfg = CoralConfig.from_dict(data)
    paths = create_project(cfg, config_dir=repo)

    # Counters are created lazily on first bump (matches Phase 1's behavior);
    # what we DO assert is that the layout permits them to exist.
    for i in range(2):
        assert (paths.coral_dir / "islands" / str(i)).is_dir()


def test_create_project_multi_island_per_island_checkpoint_repo(tmp_path):
    """Each island gets its own checkpoint git repo."""
    repo = tmp_path / "myrepo"
    (repo / "src").mkdir(parents=True)

    data = _base_config_dict(repo)
    data["islands"] = {"count": 2}
    cfg = CoralConfig.from_dict(data)
    paths = create_project(cfg, config_dir=repo)

    for i in range(2):
        assert (paths.coral_dir / "islands" / str(i) / ".git").is_dir(), (
            f"island {i} has no checkpoint .git"
        )


def test_setup_shared_state_single_island_keeps_public_target(tmp_path):
    """No island_id → symlinks resolve to coral_dir/public/* (today's behavior)."""
    coral_dir = tmp_path / ".coral"
    (coral_dir / "public" / "notes").mkdir(parents=True)
    (coral_dir / "public" / "attempts").mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    setup_shared_state(worktree, coral_dir, ".claude", island_id=None)

    notes_link = worktree / ".claude" / "notes"
    assert notes_link.is_symlink()
    assert notes_link.resolve() == (coral_dir / "public" / "notes").resolve()


def test_setup_shared_state_multi_island_targets_island_root(tmp_path):
    """island_id="1" → symlinks resolve to coral_dir/islands/1/*."""
    coral_dir = tmp_path / ".coral"
    (coral_dir / "islands" / "1" / "notes").mkdir(parents=True)
    (coral_dir / "islands" / "1" / "attempts").mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    setup_shared_state(worktree, coral_dir, ".claude", island_id="1")

    notes_link = worktree / ".claude" / "notes"
    assert notes_link.is_symlink()
    assert notes_link.resolve() == (coral_dir / "islands" / "1" / "notes").resolve()


def test_setup_shared_state_writes_coral_island_breadcrumb(tmp_path):
    """Multi-island setup writes the island id to .coral_island in the worktree."""
    coral_dir = tmp_path / ".coral"
    (coral_dir / "islands" / "2" / "notes").mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    setup_shared_state(worktree, coral_dir, ".claude", island_id="2")

    bc = worktree / ".coral_island"
    assert bc.exists()
    assert bc.read_text().strip() == "2"


def test_setup_shared_state_single_island_does_not_write_breadcrumb(tmp_path):
    """Single-island setup must NOT leave a .coral_island file."""
    coral_dir = tmp_path / ".coral"
    (coral_dir / "public" / "notes").mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    setup_shared_state(worktree, coral_dir, ".claude", island_id=None)

    assert not (worktree / ".coral_island").exists()
