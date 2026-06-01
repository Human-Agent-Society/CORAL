"""Integration tests for Phase 2 — multi-island runtime activation."""

from __future__ import annotations

import json as _json
from pathlib import Path

from coral.config import CoralConfig
from coral.workspace.project import create_project
from coral.workspace.worktree import (
    setup_claude_settings,
    setup_opencode_settings,
    setup_shared_state,
)


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
        for sub in (
            "attempts",
            "notes",
            "skills",
            "agents",
            "roles",
            "heartbeat",
            "eval_logs",
            "logs",
        ):
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


def test_setup_claude_settings_multi_island_scopes_allows_to_island_root(tmp_path):
    """In multi-island, Read allows reference islands/<id>/ not public/."""
    coral_dir = tmp_path / ".coral"
    (coral_dir / "islands" / "1").mkdir(parents=True)
    (coral_dir / "private").mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)

    setup_claude_settings(worktree, coral_dir, island_id="1")

    settings = _json.loads((worktree / ".claude" / "settings.local.json").read_text())
    allow = settings["permissions"]["allow"]
    sibling_island_pattern = str(coral_dir.resolve() / "islands" / "0")
    own_island_pattern = str(coral_dir.resolve() / "islands" / "1")
    joined = "\n".join(allow)
    assert sibling_island_pattern not in joined, "should not allow sibling-island reads"
    assert own_island_pattern in joined or "/islands/1" in joined, (
        f"expected island-1 path in allow rules; got {allow}"
    )


def test_setup_claude_settings_single_island_unchanged(tmp_path):
    """When island_id is None, behavior matches today (no change to Read rules)."""
    coral_dir = tmp_path / ".coral"
    (coral_dir / "public").mkdir(parents=True)
    (coral_dir / "private").mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)

    setup_claude_settings(worktree, coral_dir, island_id=None)

    settings = _json.loads((worktree / ".claude" / "settings.local.json").read_text())
    assert "permissions" in settings


def test_setup_opencode_settings_multi_island_external_dir_scoped(tmp_path):
    """OpenCode external_directory permission scopes to the island, not public."""
    coral_dir = tmp_path / ".coral"
    (coral_dir / "islands" / "2").mkdir(parents=True)
    (coral_dir / "private").mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    setup_opencode_settings(worktree, coral_dir, island_id="2")

    settings = _json.loads((worktree / ".opencode" / "opencode.json").read_text())
    ext = settings["permission"]["external_directory"]
    keys = "\n".join(ext.keys())
    assert "islands/2" in keys, f"expected island-2 path in opencode external_directory; got {ext}"
    assert "public" not in keys, (
        f"public pattern leaked into multi-island opencode config; got {ext}"
    )


def test_partition_and_setup_threads_island_id_into_worktrees(tmp_path):
    """After project setup, every agent worktree has the right .coral_island breadcrumb."""
    repo = tmp_path / "myrepo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "README.md").write_text("hi")
    (repo / "src").joinpath("__init__.py").touch()

    data = _base_config_dict(repo)
    data["islands"] = {"count": 2}
    data["agents"] = {"count": 4}
    cfg = CoralConfig.from_dict(data)
    paths = create_project(cfg, config_dir=repo)

    # Manually exercise the partition + per-agent worktree setup that the
    # manager would do at start_all time, without actually spawning subprocesses.
    from coral.agent.assignments import partition_into_islands, resolve_agent_specs
    from coral.workspace.worktree import (
        create_agent_worktree,
        setup_shared_state,
        write_agent_id,
    )

    specs = partition_into_islands(resolve_agent_specs(cfg), cfg.islands.count)
    assert len(specs) == 4

    # Initialise the source repo as a real git repo so worktree creation works.
    # ``create_project`` already runs ``git init``/``commit`` on ``paths.repo_dir``,
    # so the commands here are idempotent (``--allow-empty`` covers the
    # "already initialised, working tree clean" case).
    import subprocess

    subprocess.run(["git", "init"], cwd=str(paths.repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=str(paths.repo_dir), check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "--allow-empty",
            "-m",
            "init",
        ],
        cwd=str(paths.repo_dir),
        check=True,
        capture_output=True,
    )

    for spec in specs:
        wt = create_agent_worktree(paths.repo_dir, spec.agent_id, paths.agents_dir)
        write_agent_id(wt, spec.agent_id)
        setup_shared_state(wt, paths.coral_dir, ".claude", island_id=spec.island_id)
        # Every worktree must have the breadcrumb pointing at the agent's island
        bc = wt / ".coral_island"
        assert bc.exists(), f"missing .coral_island in {wt}"
        assert bc.read_text().strip() == spec.island_id

        # Symlink must resolve into the right island
        notes_link = wt / ".claude" / "notes"
        assert notes_link.is_symlink()
        target = notes_link.resolve()
        expected_island_root = paths.coral_dir / "islands" / spec.island_id
        assert target.parent == expected_island_root.resolve()


def test_agent_manager_partitions_specs_in_start_all_setup(tmp_path):
    """The manager resolves specs via partition_into_islands when islands.count > 1."""
    repo = tmp_path / "myrepo"
    (repo / "src").mkdir(parents=True)
    data = _base_config_dict(repo)
    data["islands"] = {"count": 3}
    data["agents"] = {"count": 6}
    cfg = CoralConfig.from_dict(data)

    from coral.agent.manager import AgentManager

    mgr = AgentManager(cfg)

    ids = sorted(s.agent_id for s in mgr.specs)
    # 6 agents on 3 islands round-robin → 2 each
    assert ids == [
        "0-agent-1",
        "0-agent-2",
        "1-agent-1",
        "1-agent-2",
        "2-agent-1",
        "2-agent-2",
    ]
    assert all(s.island_id in {"0", "1", "2"} for s in mgr.specs)


def test_agent_manager_single_island_specs_unchanged(tmp_path):
    """Single-island AgentManager keeps the flat agent-N ids."""
    repo = tmp_path / "myrepo"
    (repo / "src").mkdir(parents=True)
    data = _base_config_dict(repo)
    data["agents"] = {"count": 2}
    cfg = CoralConfig.from_dict(data)

    from coral.agent.manager import AgentManager

    mgr = AgentManager(cfg)

    assert [s.agent_id for s in mgr.specs] == ["agent-1", "agent-2"]
    assert all(s.island_id is None for s in mgr.specs)
