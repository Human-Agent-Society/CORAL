# Multi-Island Phase 2 — Runtime Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After this plan, setting `islands.count: N` in `task.yaml` actually creates N isolated islands on disk, partitions the agents across them, and routes every `coral eval` + grader read/write to the correct island. End state: multi-island runs work end-to-end except for the migration cycle itself (deferred to Phase 3).

**Architecture:** Phase 1 already shipped the plumbing — config dataclasses, `island_root()` resolver, every hub module accepts an optional `island_id`. Phase 2 *wires* that plumbing into the runtime: the workspace setup creates per-island subtrees, the manager partitions agents round-robin across islands and tags each one with a globally-unique `<birth_island>-agent-<seq>` ID, the per-agent worktree symlinks target the right island, `submit_eval` reads a `.coral_island` breadcrumb, and the grader daemon scans every island's attempts dir.

**Tech Stack:** Python 3.11+, dataclasses, OmegaConf, pytest, subprocess (git worktree management). No new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-31-multi-island-design.md` §4.1, §4.2, §4.4-4.9, §6.5 (process lifecycle is informational only — Phase 3 implements the migration cycle itself).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `coral/agent/assignments.py` | Modify | Add `island_id` field to `AgentSpec`. Add `partition_into_islands(specs, count)` helper that distributes agents round-robin and rewrites IDs to `<birth_island>-agent-<seq>`. |
| `coral/workspace/project.py` | Modify | When `config.islands.count > 1`, build the `islands/<id>/` tree (one subtree per island), seed bundled skills/agents per-island, init per-island checkpoint repo + per-island eval counter, and create the global eval counter at `.coral/eval_count`. |
| `coral/workspace/worktree.py` | Modify | `setup_shared_state(worktree, coral_dir, shared_dir_name, island_id=None)` — symlinks target `islands/<id>/*` when island_id is set, write a `.coral_island` breadcrumb. The four `setup_*_settings` writers gain `island_id` so their allow/deny path patterns scope to the right island. |
| `coral/template/coral_md.py` | Modify | `generate_coral_md(..., island_id=None)` — when multi-island, append a short paragraph telling the agent which island it lives on and that other islands evolve independently. |
| `coral/agent/manager.py` | Modify | `start_all` partitions specs via `partition_into_islands`. `_setup_and_start_agent` gains `island_id` and threads it into every downstream call. New `_agent_island: dict[str, str]` mapping lookup so heartbeat / monitor loops know which island an agent belongs to. `monitor_loop`'s attempt-scanning + heartbeat reads become island-aware. |
| `coral/hooks/post_commit.py` | Modify | `submit_eval` reads the new `.coral_island` breadcrumb, stamps `metadata.island_id` on the Attempt, and writes via `write_attempt(coral_dir, attempt, island_id=...)`. The hardcoded `public/attempts/` parent-lookup is replaced by an island-aware path. |
| `coral/grader/daemon.py` | Modify | `_find_pending` scans `islands/*/attempts/*.json` in multi-island mode, falls back to `public/attempts/*.json` in single-island. `_grade_one` recovers `island_id` from `attempt.metadata` and passes it to every hub-module call (`write_attempt`, `increment_eval_count`, `get_agent_attempts`). |
| `tests/test_islands_runtime.py` | Create | Integration-style tests that build a multi-island project, partition agents, verify the on-disk layout, run a synthetic eval through the daemon, and confirm island isolation. |
| `tests/test_assignments.py` | Modify | Add tests for `partition_into_islands`. |

---

## Task 1: `partition_into_islands` + `AgentSpec.island_id`

**Files:**
- Modify: `coral/agent/assignments.py`
- Modify: `tests/test_assignments.py`

- [ ] **Step 1: Write failing tests for `partition_into_islands`**

Append to `tests/test_assignments.py` (create the file if it doesn't exist — but it does):

```python
from coral.agent.assignments import (
    AgentSpec,
    partition_into_islands,
    resolve_agent_specs,
)


def _bare_spec(agent_id: str) -> AgentSpec:
    return AgentSpec(
        agent_id=agent_id,
        runtime="claude_code",
        model="sonnet",
        runtime_options={},
        assignment_index=None,
    )


def test_partition_single_island_returns_specs_unchanged():
    """count=1 = single-island = no ID rewrite, no island_id, identity."""
    specs = [_bare_spec("agent-1"), _bare_spec("agent-2")]
    out = partition_into_islands(specs, count=1)
    assert [s.agent_id for s in out] == ["agent-1", "agent-2"]
    assert all(s.island_id is None for s in out)


def test_partition_round_robin_distributes_specs():
    """count=3 with 6 agents: each island gets 2 agents."""
    specs = [_bare_spec(f"agent-{i + 1}") for i in range(6)]
    out = partition_into_islands(specs, count=3)
    by_island: dict[str, list[str]] = {}
    for s in out:
        by_island.setdefault(s.island_id, []).append(s.agent_id)
    assert sorted(by_island) == ["0", "1", "2"]
    # Round-robin: agent-1→0, agent-2→1, agent-3→2, agent-4→0, ...
    assert by_island["0"] == ["0-agent-1", "0-agent-2"]
    assert by_island["1"] == ["1-agent-1", "1-agent-2"]
    assert by_island["2"] == ["2-agent-1", "2-agent-2"]


def test_partition_rewrites_agent_ids_with_birth_island_prefix():
    """Multi-island IDs are <birth_island>-agent-<per-island-seq>."""
    specs = [_bare_spec(f"agent-{i + 1}") for i in range(4)]
    out = partition_into_islands(specs, count=2)
    # 0-agent-1, 1-agent-1, 0-agent-2, 1-agent-2
    assert [s.agent_id for s in out] == [
        "0-agent-1",
        "1-agent-1",
        "0-agent-2",
        "1-agent-2",
    ]


def test_partition_preserves_runtime_and_model():
    """Partition must not perturb the underlying runtime/model/options of each spec."""
    specs = [
        AgentSpec(
            agent_id="agent-1",
            runtime="claude_code",
            model="sonnet",
            runtime_options={"foo": "bar"},
        ),
        AgentSpec(
            agent_id="agent-2",
            runtime="codex",
            model="gpt-5.4",
            runtime_options={},
        ),
    ]
    out = partition_into_islands(specs, count=2)
    by_id = {s.agent_id: s for s in out}
    assert by_id["0-agent-1"].runtime == "claude_code"
    assert by_id["0-agent-1"].runtime_options == {"foo": "bar"}
    assert by_id["1-agent-1"].runtime == "codex"
    assert by_id["1-agent-1"].model == "gpt-5.4"


def test_partition_raises_on_count_zero():
    import pytest
    with pytest.raises(ValueError, match="count must be >= 1"):
        partition_into_islands([_bare_spec("agent-1")], count=0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/pingu/posttrain/projects/has/CORAL/.claude/worktrees/feat+multi-island
uv run pytest tests/test_assignments.py -v -k partition
```

Expected: FAIL — `ImportError: cannot import name 'partition_into_islands' from 'coral.agent.assignments'`.

- [ ] **Step 3: Add `island_id` field to `AgentSpec`**

In `coral/agent/assignments.py`, add a single new field (with default `None`) to the `@dataclass(frozen=True) class AgentSpec`:

```python
@dataclass(frozen=True)
class AgentSpec:
    """Concrete spawn parameters for a single agent."""

    agent_id: str
    runtime: str
    model: str
    runtime_options: dict[str, Any] = field(default_factory=dict)
    # Index into ``agents.assignments`` this agent came from, or None when the
    # run is in uniform mode (no assignments list).
    assignment_index: int | None = None
    # Birth island ID after partitioning (e.g. "0", "1"). None in single-island
    # mode. Stable across migration — the prefix on ``agent_id`` always reflects
    # birth island, while this field can be repointed in Phase 3 if needed.
    island_id: str | None = None
```

- [ ] **Step 4: Add `partition_into_islands` helper**

Append to `coral/agent/assignments.py`:

```python
def partition_into_islands(
    specs: list[AgentSpec],
    count: int,
) -> list[AgentSpec]:
    """Distribute resolved agent specs across `count` islands round-robin.

    Returns a new list of AgentSpecs with ``island_id`` populated and
    ``agent_id`` rewritten to ``<birth_island>-agent-<per-island-seq>``
    when count > 1. When count == 1, returns the input unchanged (no
    ID rewriting, ``island_id`` stays None) — preserves today's single-island
    behavior exactly.

    Round-robin: spec i lands on island ``i % count``. The per-island sequence
    is the order each island sees specs (so the first spec landing on island 2
    is ``2-agent-1`` regardless of its global index).

    Raises:
        ValueError: if count < 1.
    """
    if count < 1:
        raise ValueError(f"count must be >= 1, got {count}")
    if count == 1:
        return list(specs)

    per_island_seq: dict[str, int] = {}
    out: list[AgentSpec] = []
    for global_idx, spec in enumerate(specs):
        island_id = str(global_idx % count)
        per_island_seq[island_id] = per_island_seq.get(island_id, 0) + 1
        seq = per_island_seq[island_id]
        new_id = f"{island_id}-agent-{seq}"
        out.append(
            AgentSpec(
                agent_id=new_id,
                runtime=spec.runtime,
                model=spec.model,
                runtime_options=dict(spec.runtime_options),
                assignment_index=spec.assignment_index,
                island_id=island_id,
            )
        )
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_assignments.py -v -k partition
```

Expected: PASS (5 new tests).

- [ ] **Step 6: Run the full assignments test suite to confirm no regression**

```bash
uv run pytest tests/test_assignments.py -v
```

Expected: all pre-existing tests still PASS.

- [ ] **Step 7: Commit**

```bash
git add coral/agent/assignments.py tests/test_assignments.py
git commit -m "feat(agent): partition specs across islands with birth-prefixed ids"
```

---

## Task 2: `create_project` builds per-island subtrees

**Files:**
- Modify: `coral/workspace/project.py`
- Modify: `tests/test_islands_runtime.py` (create)

- [ ] **Step 1: Write failing tests for multi-island project setup**

Create `tests/test_islands_runtime.py`:

```python
"""Integration tests for Phase 2 — multi-island runtime activation."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from coral.config import CoralConfig
from coral.workspace.project import create_project


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
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
uv run pytest tests/test_islands_runtime.py -v
```

Expected: 4 FAIL (`single_island` may pass already). FAILs: multi-island tests expect `islands/` subdir.

- [ ] **Step 3: Update `coral/workspace/project.py` to build per-island layout**

In `coral/workspace/project.py`, locate the section in `create_project` that calls `(coral_dir / "public" / "attempts").mkdir(...)` etc. (around line 150-160). Wrap the per-island state creation in a new helper and call it once for `public` (single-island) or once per island (multi-island).

```python
# Near the top of the module, after _ROLE_TEMPLATE_PATH definition:
_PER_ISLAND_SUBDIRS = (
    "attempts",
    "logs",
    "skills",
    "agents",
    "notes",
    "heartbeat",
    "eval_logs",
    "roles",
)


def _build_island_subtree(
    coral_dir: Path,
    island_root: Path,
    effective_config_dir: Path,
    user_skill_paths: list[str],
) -> None:
    """Create the per-island state directory tree and seed bundled assets.

    Used once for `public/` in single-island mode, and once per `islands/<id>/`
    in multi-island mode. Seeds bundled skills + bundled subagent templates
    + initializes the checkpoint git repo for this island.
    """
    for sub in _PER_ISLAND_SUBDIRS:
        (island_root / sub).mkdir(parents=True, exist_ok=True)

    # Seed bundled skills
    if _SEED_SKILLS_DIR.is_dir():
        for skill_dir in _SEED_SKILLS_DIR.iterdir():
            if skill_dir.is_dir():
                dst = island_root / "skills" / skill_dir.name
                if not dst.exists():
                    shutil.copytree(skill_dir, dst)

    # Seed user-provided skills from config
    for skill_path in user_skill_paths:
        src = Path(skill_path)
        if not src.is_absolute():
            src = (effective_config_dir / src).resolve()
        if src.is_dir():
            dst = island_root / "skills" / src.name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            logger.warning(f"Skill directory not found: {src}")

    # Seed bundled subagent templates
    if _SEED_AGENTS_DIR.is_dir():
        for agent_file in _SEED_AGENTS_DIR.iterdir():
            if agent_file.is_file():
                dst = island_root / "agents" / agent_file.name
                if not dst.exists():
                    shutil.copy2(agent_file, dst)

    # Per-island checkpoint git repo (one .git per island, scoped locks)
    init_checkpoint_repo(str(coral_dir), island_id=_island_id_from_root(coral_dir, island_root))


def _island_id_from_root(coral_dir: Path, island_root: Path) -> str | None:
    """Return the island_id implied by island_root, or None for single-island."""
    try:
        rel = island_root.resolve().relative_to((coral_dir / "islands").resolve())
        # rel is like Path("0"); take first segment
        return str(rel).split("/", 1)[0] if str(rel) and str(rel) != "." else None
    except ValueError:
        return None
```

Then in `create_project`, replace the block that hardcodes `coral_dir/public/...` creation with a branch on `config.islands.count`:

```python
    # Create shared state directories.
    # Single-island (count == 1): keep today's exact layout under public/.
    # Multi-island (count > 1):   build islands/<id>/ subtree per island, leave
    #                              public/ minimal (only global meta).
    (coral_dir / "public").mkdir(parents=True, exist_ok=True)
    (coral_dir / "private").mkdir(parents=True, exist_ok=True)
    agents_dir.mkdir(parents=True, exist_ok=True)

    if config.islands.count == 1:
        _build_island_subtree(
            coral_dir,
            coral_dir / "public",
            effective_config_dir,
            list(config.agents.skills),
        )
    else:
        (coral_dir / "islands").mkdir(parents=True, exist_ok=True)
        for i in range(config.islands.count):
            island_root = coral_dir / "islands" / str(i)
            island_root.mkdir(parents=True, exist_ok=True)
            _build_island_subtree(
                coral_dir,
                island_root,
                effective_config_dir,
                list(config.agents.skills),
            )

    # `effective_config_dir` is computed right after this block in the existing
    # function; if your insertion places this block before that variable is
    # bound, move the `effective_config_dir = ...` line up.
```

The existing single-island seeding block (the `for skill_dir in seed_skills_dir.iterdir():` loop further down) becomes redundant — delete it. Same for the existing `init_checkpoint_repo(str(coral_dir))` call further down — `_build_island_subtree` now handles it for every layout.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/test_islands_runtime.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Run the full workspace + hub test suite to confirm no regression**

```bash
uv run pytest tests/test_workspace.py tests/test_hub.py tests/test_islands.py tests/test_checkpoint.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add coral/workspace/project.py tests/test_islands_runtime.py
git commit -m "feat(workspace): create per-island subtrees when islands.count > 1"
```

---

## Task 3: `setup_shared_state` + `.coral_island` breadcrumb

**Files:**
- Modify: `coral/workspace/worktree.py`
- Modify: `tests/test_islands_runtime.py`

- [ ] **Step 1: Write failing tests for breadcrumb + island-aware symlinks**

Append to `tests/test_islands_runtime.py`:

```python
from coral.workspace.worktree import (
    get_coral_dir,
    setup_shared_state,
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_islands_runtime.py -v -k "shared_state or breadcrumb"
```

Expected: FAIL — `TypeError: setup_shared_state() got an unexpected keyword argument 'island_id'`.

- [ ] **Step 3: Update `setup_shared_state` in `coral/workspace/worktree.py`**

Replace the existing `setup_shared_state` body (around lines 148-214) with this version:

```python
def setup_shared_state(
    worktree_path: Path,
    coral_dir: Path,
    shared_dir_name: str = ".claude",
    island_id: str | int | None = None,
) -> None:
    """Create a shared state directory in the worktree with symlinks into the island root.

    Symlinks notes, skills, attempts, etc. from the per-island state root into
    the shared directory so agents can read/write shared state. In single-island
    mode (``island_id is None``) the target is ``coral_dir/public/*``; in
    multi-island mode it is ``coral_dir/islands/<id>/*``.

    When ``island_id`` is provided, also writes a ``.coral_island`` breadcrumb
    in the worktree so ``coral eval`` and other CLI commands can determine which
    island this agent belongs to without rescanning configuration.

    Args:
        worktree_path: Path to the agent's git worktree
        coral_dir: Path to the shared .coral directory
        shared_dir_name: Name of the shared dir in the worktree (e.g. ".claude")
        island_id: The agent's island id (str/int), or None for single-island mode.
    """
    from coral.hub._island import island_root

    state_root = island_root(coral_dir, island_id)
    shared_dir = worktree_path / shared_dir_name

    # Self-heal old-style absolute symlink to .coral/public/.
    if shared_dir.is_symlink():
        shared_dir.unlink()

    shared_dir.mkdir(exist_ok=True)

    shared_items = [
        "notes",
        "skills",
        "agents",
        "attempts",
        "logs",
        "heartbeat",
        "roles",
        "eval_logs",
    ]
    for item in shared_items:
        src = state_root / item
        dst = shared_dir / item
        # If a previous (buggy) run wrote into a real local dir at this path
        # instead of a symlink, migrate any files into the shared dir then
        # replace the local dir with a symlink.
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

    # Write the .coral_island breadcrumb when on an island. Single-island
    # callers (no island_id) deliberately do NOT get this file — its absence
    # is how downstream code (submit_eval, monitor_loop) distinguishes modes.
    if island_id is not None:
        (worktree_path / ".coral_island").write_text(str(island_id))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/test_islands_runtime.py -v -k "shared_state or breadcrumb"
```

Expected: 4 PASS.

- [ ] **Step 5: Run pre-existing workspace tests to confirm no regression**

```bash
uv run pytest tests/test_workspace.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add coral/workspace/worktree.py tests/test_islands_runtime.py
git commit -m "feat(workspace): setup_shared_state targets island root + writes .coral_island"
```

---

## Task 4: Permission settings scope to island root

**Files:**
- Modify: `coral/workspace/worktree.py` (all four `setup_*_settings` functions)
- Modify: `tests/test_islands_runtime.py`

- [ ] **Step 1: Write failing tests for island-scoped Claude/OpenCode permissions**

Append to `tests/test_islands_runtime.py`:

```python
import json as _json

from coral.workspace.worktree import (
    setup_claude_settings,
    setup_opencode_settings,
)


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
    # The Read allow that today references `.coral/public/**` should now
    # reference `.coral/islands/1/**` in multi-island mode. We don't enforce
    # the EXACT format — only that no `public` substring appears in the
    # multi-island scoped patterns and that "islands/1" does.
    sibling_island_pattern = str(coral_dir.resolve() / "islands" / "0")
    own_island_pattern = str(coral_dir.resolve() / "islands" / "1")
    # The agent on island 1 must NOT have permission to read island 0's state.
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
    # Bash, Edit, Write allows are unchanged (they refer to worktree paths, not coral_dir).
    # We just confirm the file was written successfully.
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
    # The external_directory key today is the public pattern. In multi-island
    # mode it should be the island-2 pattern. We accept either glob form.
    keys = "\n".join(ext.keys())
    assert "islands/2" in keys, f"expected island-2 path in opencode external_directory; got {ext}"
    assert "public" not in keys, f"public pattern leaked into multi-island opencode config; got {ext}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_islands_runtime.py -v -k "claude_settings or opencode_settings"
```

Expected: FAIL — `TypeError: setup_claude_settings() got an unexpected keyword argument 'island_id'`.

- [ ] **Step 3: Add `island_id` parameter to the four `setup_*_settings` functions**

The pattern is the same for each. Modify `setup_claude_settings` in `coral/workspace/worktree.py` like this:

```python
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
    # In multi-island, restrict Read access to THIS island only.
    # In single-island, the bundled framework agents/ live under public/agents/
    # (the existing path); keep that for backwards-compatible permission scope.
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
        "defaultMode": "auto",
        "allow": allow_rules,
        "deny": deny_rules,
    }

    settings: dict = {"permissions": permissions}

    if gateway_url or gateway_api_key:
        env: dict[str, str] = {}
        if gateway_url:
            env["ANTHROPIC_BASE_URL"] = gateway_url
        if gateway_api_key:
            env["ANTHROPIC_API_KEY"] = gateway_api_key
        env["ANTHROPIC_CUSTOM_HEADERS"] = ""
        settings["env"] = env

    settings_path = claude_dir / "settings.local.json"
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
```

Then make the same `island_id: str | int | None = None` addition to `setup_opencode_settings`, `setup_codex_settings`, and `setup_cursor_settings`. For each, replace any hardcoded `coral_dir / "public"` reference with `island_root(coral_dir, island_id)`. For `setup_opencode_settings`, replace the `public_pattern = str(coral_dir.resolve() / "public") + "/**"` line with `state_root_pattern = str(island_root(coral_dir, island_id).resolve()) + "/**"` and use that in the `external_directory` block.

`setup_codex_settings` doesn't reference coral_dir paths in its config.toml output — it only sets model/sandbox/etc. — so just add the `island_id` keyword for signature uniformity, do not change the body.

`setup_cursor_settings` writes a rules .mdc file that mentions `private_dir`. The mention of `private_dir` is unchanged (private is global). For multi-island, also mention the island root in the "share findings through `.cursor/notes/`" line — but since this is a prose nudge for the agent, keep it generic; just add the `island_id` parameter for uniformity, no body change required.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/test_islands_runtime.py -v -k "claude_settings or opencode_settings"
```

Expected: 3 PASS.

- [ ] **Step 5: Run pre-existing workspace tests to confirm no regression**

```bash
uv run pytest tests/test_workspace.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add coral/workspace/worktree.py tests/test_islands_runtime.py
git commit -m "feat(workspace): scope runtime permission settings to per-island root"
```

---

## Task 5: `generate_coral_md` mentions island in multi-island mode

**Files:**
- Modify: `coral/template/coral_md.py`
- Modify: `tests/test_template.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_template.py`:

```python
def test_generate_coral_md_single_island_has_no_island_mention():
    """Without island_id, no provenance hint about islands is in the output."""
    from coral.config import CoralConfig
    from coral.template.coral_md import generate_coral_md

    cfg = CoralConfig.from_dict({"task": {"name": "t", "description": "d"}})
    md = generate_coral_md(cfg, agent_id="agent-1")
    assert "island" not in md.lower()


def test_generate_coral_md_multi_island_mentions_island(tmp_path):
    """With island_id and islands.count > 1, the prompt mentions the agent's island."""
    from coral.config import CoralConfig
    from coral.template.coral_md import generate_coral_md

    cfg = CoralConfig.from_dict({
        "task": {"name": "t", "description": "d"},
        "islands": {"count": 4},
    })
    md = generate_coral_md(cfg, agent_id="2-agent-1", island_id="2")
    md_lower = md.lower()
    assert "island" in md_lower
    # Names the concrete island id so the agent has unambiguous orientation
    assert "island `2`" in md or "island 2" in md, "expected mention of island 2"
```

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_template.py -v -k island
```

Expected: FAIL — `TypeError: generate_coral_md() got an unexpected keyword argument 'island_id'`.

- [ ] **Step 3: Update `generate_coral_md`**

In `coral/template/coral_md.py`, change the signature and append the multi-island paragraph:

```python
def generate_coral_md(
    config: CoralConfig,
    agent_id: str,
    single_agent: bool = False,
    shared_dir: str = ".claude",
    island_id: str | int | None = None,
) -> str:
    """Produce the CORAL.md file that agents read at startup.

    Args:
        config: The coral config
        agent_id: This agent's ID
        single_agent: If True, use simplified single-agent template
        shared_dir: Name of the shared state directory
        island_id: Agent's island in multi-island mode (formats a provenance hint)
    """
    template_path = _SINGLE_TEMPLATE_PATH if single_agent else _TEMPLATE_PATH
    template = template_path.read_text()

    # ... existing body (tips_section, score_direction, research_section etc.) ...

    rendered = template.format(
        task_name=config.task.name,
        task_description=config.task.description,
        tips_section=tips_section,
        score_direction=score_direction,
        agent_id=agent_id,
        shared_dir=shared_dir,
        workflow_summary=workflow_summary,
        research_section=research_section,
        plan_step_num=step_offset,
        edit_step_num=step_offset + 1,
        eval_step_num=step_offset + 2,
        results_step_num=step_offset + 3,
        knowledge_step_num=step_offset + 4,
        research_back_reference=research_back_reference,
        repeat_research_hint=repeat_research_hint,
    )

    # Multi-island provenance hint: append once at the end so the existing
    # template stays untouched. Only when there's actually more than one island.
    if island_id is not None and config.islands.count > 1:
        rendered += (
            "\n\n## Multi-island provenance\n\n"
            f"You are working on island `{island_id}` in a multi-island run "
            f"({config.islands.count} islands total). Other islands exist with "
            "their own attempts, notes, and skills, but you cannot see their "
            "state directly. Each island evolves independently.\n"
        )

    return rendered
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/test_template.py -v -k island
```

Expected: PASS (2 new tests).

- [ ] **Step 5: Run the existing template tests to confirm no regression**

```bash
uv run pytest tests/test_template.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add coral/template/coral_md.py tests/test_template.py
git commit -m "feat(template): generate_coral_md mentions island in multi-island runs"
```

---

## Task 6: `_setup_and_start_agent` threads `island_id` through every downstream call

**Files:**
- Modify: `coral/agent/manager.py`
- Modify: `tests/test_islands_runtime.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_islands_runtime.py`:

```python
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

    # Initialise the source repo as a real git repo so worktree creation works
    import subprocess
    subprocess.run(["git", "init"], cwd=str(paths.repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=str(paths.repo_dir), check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init"],
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
```

- [ ] **Step 2: Run it to verify the failure mode**

```bash
uv run pytest tests/test_islands_runtime.py::test_partition_and_setup_threads_island_id_into_worktrees -v
```

Expected: passes only after the relevant `_setup_and_start_agent` changes are in place. Since the test itself manually calls the workspace primitives (`setup_shared_state` already takes `island_id` from Task 3), it should ALREADY pass after Task 3 — this test is really a forward-looking integration regression gate. If it passes, that's fine; commit it alongside Task 6's manager work.

- [ ] **Step 3: Thread `island_id` through `_setup_and_start_agent`**

In `coral/agent/manager.py`, modify `_setup_and_start_agent`:

- Add a new parameter: `island_id: str | None = None`.
- Pass `island_id` to `setup_shared_state(worktree_path, self.paths.coral_dir, shared_dir_name, island_id=island_id)`.
- For the four `setup_*_settings` calls (around lines 435-466), add `island_id=island_id` to each call.
- For the `generate_coral_md(self.config, agent_id, single_agent=single_agent, shared_dir=shared_dir_name)` call, add `island_id=island_id`.
- Maintain a manager-side mapping: in `__init__`, initialize `self._agent_island: dict[str, str] = {}`. In `_setup_and_start_agent`, write `self._agent_island[agent_id] = island_id` when `island_id is not None`.

- [ ] **Step 4: Run the integration test to verify it passes**

```bash
uv run pytest tests/test_islands_runtime.py::test_partition_and_setup_threads_island_id_into_worktrees -v
```

Expected: PASS.

- [ ] **Step 5: Run the manager test suite to confirm no regression**

```bash
uv run pytest tests/test_manager_reliability.py tests/test_assignments.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add coral/agent/manager.py tests/test_islands_runtime.py
git commit -m "feat(manager): thread island_id through agent setup pipeline"
```

---

## Task 7: `AgentManager.start_all` partitions specs across islands

**Files:**
- Modify: `coral/agent/manager.py`
- Modify: `tests/test_islands_runtime.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_islands_runtime.py`:

```python
def test_agent_manager_partitions_specs_in_start_all_setup(tmp_path):
    """The manager resolves specs via partition_into_islands when islands.count > 1.

    We don't actually spawn subprocesses — we just verify the spec resolution
    step the manager does in __init__ produces island-prefixed ids.
    """
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
        "0-agent-1", "0-agent-2",
        "1-agent-1", "1-agent-2",
        "2-agent-1", "2-agent-2",
    ]
    # _agent_island should be populated for each (filled at setup time, not in
    # __init__) — we just confirm `specs` are all on islands here.
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
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_islands_runtime.py -v -k agent_manager_partitions
```

Expected: FAIL — specs still flat `agent-1`, `agent-2` etc.

- [ ] **Step 3: Wire `partition_into_islands` into `AgentManager.__init__`**

In `coral/agent/manager.py`, modify the `__init__`:

```python
from coral.agent.assignments import (
    AgentSpec,
    partition_into_islands,
    resolve_agent_specs,
)


class AgentManager:
    def __init__(
        self,
        config: CoralConfig,
        verbose: bool = False,
        config_dir: Path | None = None,
    ) -> None:
        self.config = config
        self.config_dir = config_dir
        # Resolve concrete per-agent specs and (when multi-island) partition them
        # across islands round-robin. Single-island returns specs unchanged.
        base_specs = resolve_agent_specs(config)
        self.specs: list[AgentSpec] = partition_into_islands(
            base_specs, count=config.islands.count
        )
        self.specs_by_id: dict[str, AgentSpec] = {s.agent_id: s for s in self.specs}
        # Per-agent island lookup (None for single-island)
        self._agent_island: dict[str, str] = {
            s.agent_id: s.island_id for s in self.specs if s.island_id is not None
        }
        # ... rest of __init__ unchanged
```

The existing `_agent_island: dict[str, str] = {}` line from Task 6 must be removed or merged with this initialization.

In `start_all`, in the per-agent loop, pass `island_id=spec.island_id`:

```python
        for i, agent_id in enumerate(agent_ids):
            spec = self.specs_by_id.get(agent_id)
            island_id = spec.island_id if spec else None
            if i > 0 and self.config.agents.stagger_seconds > 0:
                time.sleep(self.config.agents.stagger_seconds)
            shared_dir = self._runtime_for(agent_id).shared_dir_name
            handle = self._setup_and_start_agent(
                agent_id,
                island_id=island_id,
                resume_session_id=research_sessions.get(agent_id),
                prompt=warmstart.main_prompt(shared_dir) if warmstart.enabled else None,
                prompt_source="warmstart:main" if warmstart.enabled else None,
            )
            handles.append(handle)
```

Make the same `island_id` lookup at the warmstart-research and the resume_all loops where `_setup_and_start_agent` is called.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/test_islands_runtime.py -v -k agent_manager
```

Expected: 2 PASS.

- [ ] **Step 5: Run the full manager test suite**

```bash
uv run pytest tests/test_manager_reliability.py tests/test_assignments.py tests/test_warmstart.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add coral/agent/manager.py tests/test_islands_runtime.py
git commit -m "feat(manager): partition agent specs across islands at startup"
```

---

## Task 8: `submit_eval` reads `.coral_island` and writes to the right island

**Files:**
- Modify: `coral/hooks/post_commit.py`
- Modify: `tests/test_hooks.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_hooks.py`:

```python
def test_submit_eval_multi_island_writes_to_island_attempts(tmp_path, monkeypatch):
    """When .coral_island is set, submit_eval writes to islands/<id>/attempts/."""
    import subprocess

    from coral.config import CoralConfig
    from coral.hooks.post_commit import submit_eval

    # Build a minimal multi-island layout: coral_dir + a worktree
    coral_dir = tmp_path / ".coral"
    (coral_dir / "islands" / "1" / "attempts").mkdir(parents=True)
    cfg = CoralConfig.from_dict({
        "task": {"name": "t", "description": "d"},
        "islands": {"count": 2},
        "workspace": {"results_dir": str(tmp_path / "results"), "repo_path": str(tmp_path / "src")},
    })
    cfg.to_yaml(coral_dir / "config.yaml")

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=str(worktree), check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "--allow-empty", "-m", "init"], cwd=str(worktree), check=True, capture_output=True)
    (worktree / "file.txt").write_text("change")
    (worktree / ".coral_dir").write_text(str(coral_dir.resolve()))
    (worktree / ".coral_agent_id").write_text("1-agent-1")
    (worktree / ".coral_island").write_text("1")

    attempt = submit_eval(
        message="island-1 eval",
        agent_id="1-agent-1",
        workdir=str(worktree),
        wait=False,
    )

    # Attempt JSON landed in islands/1/attempts/
    expected = coral_dir / "islands" / "1" / "attempts" / f"{attempt.commit_hash}.json"
    assert expected.exists(), f"attempt was not written to {expected}"
    # Did NOT land in public/
    assert not (coral_dir / "public" / "attempts" / f"{attempt.commit_hash}.json").exists()
    # metadata.island_id stamped
    assert (attempt.metadata or {}).get("island_id") == "1"


def test_submit_eval_single_island_unchanged(tmp_path):
    """No .coral_island → today's behavior: write to public/attempts/."""
    import subprocess

    from coral.config import CoralConfig
    from coral.hooks.post_commit import submit_eval

    coral_dir = tmp_path / ".coral"
    (coral_dir / "public" / "attempts").mkdir(parents=True)
    cfg = CoralConfig.from_dict({
        "task": {"name": "t", "description": "d"},
        "workspace": {"results_dir": str(tmp_path / "results"), "repo_path": str(tmp_path / "src")},
    })
    cfg.to_yaml(coral_dir / "config.yaml")

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=str(worktree), check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "--allow-empty", "-m", "init"], cwd=str(worktree), check=True, capture_output=True)
    (worktree / "file.txt").write_text("change")
    (worktree / ".coral_dir").write_text(str(coral_dir.resolve()))
    (worktree / ".coral_agent_id").write_text("agent-1")

    attempt = submit_eval(
        message="single-island eval",
        agent_id="agent-1",
        workdir=str(worktree),
        wait=False,
    )

    expected = coral_dir / "public" / "attempts" / f"{attempt.commit_hash}.json"
    assert expected.exists()
    # No island_id stamped
    assert "island_id" not in (attempt.metadata or {})
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_hooks.py -v -k "submit_eval_multi_island or submit_eval_single_island"
```

Expected: multi-island FAIL — attempt lands in `public/attempts/`. Single-island PASS already.

- [ ] **Step 3: Update `submit_eval` to read `.coral_island` and route writes**

In `coral/hooks/post_commit.py`, add the breadcrumb read + island-aware write. Replace the body of `submit_eval` (from the comment "Git add + commit" to the final `return final`) with:

```python
    # Git add + commit
    commit_hash = _git_add_and_commit(message, str(workdir_path))
    parent_hash = _get_parent_hash(commit_hash, str(workdir_path))

    # Determine the agent's island (if any) from the .coral_island breadcrumb
    island_id: str | None = None
    bc = workdir_path / ".coral_island"
    if bc.exists():
        try:
            island_id = bc.read_text().strip() or None
        except OSError:
            island_id = None

    # Checkpoint shared state at submission time. In multi-island the checkpoint
    # repo lives at islands/<id>/.git; in single-island it lives at public/.git.
    shared_state_hash = checkpoint(str(coral_dir), agent_id, message, island_id=island_id)

    # Look up parent attempt's shared state hash for provenance chain.
    parent_shared_state_hash = None
    if parent_hash:
        from coral.hub._island import island_root

        parent_attempt_file = (
            island_root(coral_dir, island_id) / "attempts" / f"{parent_hash}.json"
        )
        if parent_attempt_file.exists():
            try:
                parent_data = json.loads(parent_attempt_file.read_text())
                parent_shared_state_hash = parent_data.get("shared_state_hash")
            except (json.JSONDecodeError, OSError):
                pass

    # Write pending record into the agent's island.
    metadata: dict = {}
    if tune:
        metadata["budget_class"] = BUDGET_CLASS_TUNE
    if island_id is not None:
        metadata["island_id"] = island_id
    attempt = Attempt(
        commit_hash=commit_hash,
        agent_id=agent_id,
        title=message,
        score=None,
        status="pending",
        parent_hash=parent_hash,
        timestamp=datetime.now(UTC).isoformat(),
        feedback="",
        shared_state_hash=shared_state_hash,
        parent_shared_state_hash=parent_shared_state_hash,
        metadata=metadata,
    )
    write_attempt(str(coral_dir), attempt, island_id=island_id)

    if not wait:
        return attempt

    if poll_timeout is None:
        grader_timeout = config.grader.timeout if config.grader.timeout > 0 else 0
        poll_timeout = max(grader_timeout * 2 + 60, 300) if grader_timeout else 3600

    final = _poll_until_graded(coral_dir, commit_hash, poll_timeout, island_id=island_id)

    try:
        final._eval_count = read_eval_count(coral_dir, island_id=island_id)  # type: ignore[attr-defined]
    except Exception:
        pass

    return final
```

Also update `_poll_until_graded` to take and use `island_id`:

```python
def _poll_until_graded(
    coral_dir: Path,
    commit_hash: str,
    timeout: float,
    island_id: str | None = None,
) -> Attempt:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        attempt = read_attempt(coral_dir, commit_hash, island_id=island_id)
        if attempt is not None and attempt.status != "pending":
            return attempt
        time.sleep(_POLL_INTERVAL_SEC)
    raise TimeoutError(
        f"Grader did not finalize attempt {commit_hash[:12]} within {timeout:.0f}s "
        f"(is the grader daemon running?)"
    )
```

And similarly thread `island_id` into the `count_agent_pending` and `agent_in_grader_queue` calls in the queue-cap check earlier in `submit_eval`. Just pass it as a keyword (they already accept it from Phase 1).

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/test_hooks.py -v -k "submit_eval_multi_island or submit_eval_single_island"
```

Expected: PASS.

- [ ] **Step 5: Run the full hooks test suite to confirm no regression**

```bash
uv run pytest tests/test_hooks.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add coral/hooks/post_commit.py tests/test_hooks.py
git commit -m "feat(hooks): submit_eval routes writes via .coral_island breadcrumb"
```

---

## Task 9: Grader daemon scans all islands + writes back island-aware

**Files:**
- Modify: `coral/grader/daemon.py`
- Modify: `tests/test_grader_daemon.py`

- [ ] **Step 1: Write failing test for multi-island daemon scan**

Append to `tests/test_grader_daemon.py`:

```python
def test_find_pending_multi_island_scans_every_island(tmp_path):
    """_find_pending picks up attempts from every islands/<id>/attempts/ dir."""
    from coral.grader.daemon import _find_pending
    from coral.hub.attempts import write_attempt
    from coral.types import Attempt

    coral_dir = tmp_path / ".coral"
    for i in range(3):
        (coral_dir / "islands" / str(i) / "attempts").mkdir(parents=True)

    a0 = Attempt(
        commit_hash="aaa000",
        agent_id="0-agent-1",
        title="x",
        score=None,
        status="pending",
        parent_hash=None,
        timestamp="2026-05-31T10:00:00Z",
        metadata={"island_id": "0"},
    )
    a1 = Attempt(
        commit_hash="bbb111",
        agent_id="1-agent-1",
        title="y",
        score=None,
        status="pending",
        parent_hash=None,
        timestamp="2026-05-31T10:01:00Z",
        metadata={"island_id": "1"},
    )
    write_attempt(coral_dir, a0, island_id="0")
    write_attempt(coral_dir, a1, island_id="1")
    # also leave an empty island
    pending = _find_pending(coral_dir)
    hashes = {a.commit_hash for a in pending}
    assert hashes == {"aaa000", "bbb111"}


def test_find_pending_single_island_unchanged(tmp_path):
    """Single-island: _find_pending scans only public/attempts/."""
    from coral.grader.daemon import _find_pending
    from coral.hub.attempts import write_attempt
    from coral.types import Attempt

    coral_dir = tmp_path / ".coral"
    (coral_dir / "public" / "attempts").mkdir(parents=True)

    a = Attempt(
        commit_hash="ccc",
        agent_id="agent-1",
        title="x",
        score=None,
        status="pending",
        parent_hash=None,
        timestamp="2026-05-31T10:00:00Z",
    )
    write_attempt(coral_dir, a)
    pending = _find_pending(coral_dir)
    assert {p.commit_hash for p in pending} == {"ccc"}
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_grader_daemon.py -v -k find_pending_multi_island
```

Expected: FAIL — daemon currently only scans `public/attempts/`.

- [ ] **Step 3: Update `_find_pending` and `_grade_one` to be island-aware**

In `coral/grader/daemon.py`, replace `_find_pending`:

```python
def _find_pending(coral_dir: Path) -> list[Attempt]:
    """Return pending attempts (across all islands in multi-island mode), oldest first."""
    if (coral_dir / "islands").exists():
        islands = sorted((coral_dir / "islands").iterdir())
        attempt_dirs = [d / "attempts" for d in islands if d.is_dir()]
    else:
        attempt_dirs = [coral_dir / "public" / "attempts"]

    pending: list[Attempt] = []
    for d in attempt_dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.json")):
            try:
                from coral.types import Attempt as _Attempt
                data = _json.loads(p.read_text())
                a = _Attempt.from_dict(data)
            except (Exception,):
                continue
            if a.status == "pending" and a.score is None:
                pending.append(a)
    pending.sort(key=lambda x: x.timestamp)
    return pending
```

(Add `import json as _json` at the top of `daemon.py` if it's not already there.)

Update `_grade_one` to pass `island_id` (read from `attempt.metadata`) through to every hub call. Locate `_grade_one` (around line 289) and change:

```python
def _grade_one(
    attempt: Attempt,
    config_path: Path,
    coral_dir: Path,
    config: CoralConfig,
) -> Attempt:
    """Grade a single pending attempt and return the finalized Attempt record."""
    island_id = (attempt.metadata or {}).get("island_id")
    # ... existing body up to the _compute_status call ...
            status = _compute_status(
                score,
                attempt.agent_id,
                attempt.commit_hash,
                coral_dir,
                minimize,
                island_id=island_id,
            )
    # ... existing finalization ...
    write_attempt(str(coral_dir), finalized, island_id=island_id)
    with _eval_count_lock:
        count = increment_eval_count(coral_dir, island_id=island_id)
    # ... existing logging
```

And update `_compute_status` signature:

```python
def _compute_status(
    score: float | None,
    agent_id: str,
    commit_hash: str,
    coral_dir: Path,
    minimize: bool,
    island_id: str | None = None,
) -> str:
    if score is None:
        return "crashed"
    prev_attempts = get_agent_attempts(str(coral_dir), agent_id, island_id=island_id)
    prev_scores = [a.score for a in prev_attempts if a.score is not None and a.commit_hash != commit_hash]
    # ... rest unchanged
```

Also update `_safe_grade_one`'s fallback `write_attempt` call to pass `island_id` (extract it from the attempt's metadata before constructing the `crashed` record).

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/test_grader_daemon.py -v -k find_pending
```

Expected: PASS.

- [ ] **Step 5: Run the full daemon test suite to confirm no regression**

```bash
uv run pytest tests/test_grader_daemon.py tests/test_subprocess_grader.py tests/test_grader.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add coral/grader/daemon.py tests/test_grader_daemon.py
git commit -m "feat(grader): daemon scans every island's attempts and writes back island-aware"
```

---

## Task 10: Manager monitor loop becomes island-aware

**Files:**
- Modify: `coral/agent/manager.py`
- Modify: `tests/test_manager_seen_attempts.py`

- [ ] **Step 1: Write failing test for multi-island attempt scanning**

Append to `tests/test_manager_seen_attempts.py`:

```python
def test_get_seen_attempts_multi_island(tmp_path):
    """In multi-island, _get_seen_attempts must scan every island's attempts dir."""
    from coral.agent.manager import AgentManager
    from coral.config import CoralConfig
    from coral.hub.attempts import write_attempt
    from coral.types import Attempt
    from coral.workspace.project import ProjectPaths

    coral_dir = tmp_path / ".coral"
    for i in range(2):
        (coral_dir / "islands" / str(i) / "attempts").mkdir(parents=True)
    a0 = Attempt(
        commit_hash="aaa",
        agent_id="0-agent-1",
        title="x",
        score=None,
        status="pending",
        parent_hash=None,
        timestamp="2026-05-31T10:00:00Z",
        metadata={"island_id": "0"},
    )
    a1 = Attempt(
        commit_hash="bbb",
        agent_id="1-agent-1",
        title="y",
        score=None,
        status="pending",
        parent_hash=None,
        timestamp="2026-05-31T10:01:00Z",
        metadata={"island_id": "1"},
    )
    write_attempt(coral_dir, a0, island_id="0")
    write_attempt(coral_dir, a1, island_id="1")

    cfg = CoralConfig.from_dict({
        "task": {"name": "t", "description": "d"},
        "islands": {"count": 2},
        "agents": {"count": 2},
    })
    mgr = AgentManager(cfg)
    mgr.paths = ProjectPaths(
        results_dir=tmp_path,
        task_dir=tmp_path,
        run_dir=tmp_path,
        coral_dir=coral_dir,
        agents_dir=tmp_path / "agents",
        repo_dir=tmp_path / "repo",
    )

    seen = mgr._get_seen_attempts()
    # Expect both attempt files surfaced regardless of island
    assert {"aaa.json", "bbb.json"} <= seen
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_manager_seen_attempts.py -v -k multi_island
```

Expected: FAIL — `_get_seen_attempts` currently only globs `public/attempts/`.

- [ ] **Step 3: Update `_get_seen_attempts`, `_filter_scored`, `_read_latest_attempt`, `_get_eval_count`**

In `coral/agent/manager.py`, replace `_get_seen_attempts` with:

```python
    def _get_seen_attempts(self) -> set[str]:
        """Get the set of attempt filenames currently in any island's attempts dir."""
        assert self.paths is not None
        coral_dir = self.paths.coral_dir
        islands_dir = coral_dir / "islands"
        if islands_dir.exists():
            seen: set[str] = set()
            for island in islands_dir.iterdir():
                attempts = island / "attempts"
                if attempts.exists():
                    seen.update(f.name for f in attempts.glob("*.json"))
            return seen
        attempts_dir = coral_dir / "public" / "attempts"
        if not attempts_dir.exists():
            return set()
        return {f.name for f in attempts_dir.glob("*.json")}
```

Update `_filter_scored` similarly:

```python
    def _filter_scored(self, new_files: set[str]) -> set[str]:
        """Return only those filenames whose attempt status is not 'pending'.

        In multi-island, an attempt with `metadata.island_id` lives at
        islands/<island_id>/attempts/<file>; otherwise public/attempts/<file>.
        We resolve the file by checking every island root first, then public.
        """
        assert self.paths is not None
        coral_dir = self.paths.coral_dir

        def _resolve(fname: str) -> Path | None:
            islands_dir = coral_dir / "islands"
            if islands_dir.exists():
                for island in islands_dir.iterdir():
                    p = island / "attempts" / fname
                    if p.exists():
                        return p
            p = coral_dir / "public" / "attempts" / fname
            return p if p.exists() else None

        scored: set[str] = set()
        for fname in new_files:
            path = _resolve(fname)
            if path is None:
                continue
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            status = data.get("status")
            if status and status != "pending":
                scored.add(fname)
        return scored
```

Apply the same multi-island-aware path resolution in `_read_latest_attempt` — use the same `_resolve` helper (extract it to a `_resolve_attempt_path(fname)` instance method to avoid duplication).

Update `_get_eval_count` to read from `coral_dir / "eval_count"` in multi-island and `coral_dir / "public" / "eval_count"` in single-island:

```python
    def _get_eval_count(self) -> int:
        """Read the current global eval count."""
        assert self.paths is not None
        coral_dir = self.paths.coral_dir
        if (coral_dir / "islands").exists():
            counter_file = coral_dir / "eval_count"
        else:
            counter_file = coral_dir / "public" / "eval_count"
        if counter_file.exists():
            try:
                return int(counter_file.read_text().strip())
            except ValueError:
                pass
        return 0
```

Update `_get_heartbeat_runner` to pass `island_id` when calling `read_agent_heartbeat` / `read_global_heartbeat`:

```python
    def _get_heartbeat_runner(self, agent_id: str) -> HeartbeatRunner:
        from coral.agent.heartbeat import HeartbeatAction

        assert self.paths is not None
        shared_dir = self._runtime_for(agent_id).shared_dir_name
        island_id = self._agent_island.get(agent_id)

        local_actions = read_agent_heartbeat(self.paths.coral_dir, agent_id, island_id=island_id)
        global_actions = read_global_heartbeat(self.paths.coral_dir, island_id=island_id)
        # ... rest unchanged
```

Update the heartbeat seeding inside `_setup_and_start_agent`:

```python
        if not read_agent_heartbeat(self.paths.coral_dir, agent_id, island_id=island_id):
            write_agent_heartbeat(
                self.paths.coral_dir, agent_id, default_local_actions(self.config),
                island_id=island_id,
            )
```

And the same for `write_global_heartbeat` in `start_all` (which is called for the global config seed):

```python
        if not read_global_heartbeat(self.paths.coral_dir):
            write_global_heartbeat(self.paths.coral_dir, default_global_actions(self.config))
```

Note: global heartbeat is GLOBAL (one config across all islands). It still lives under `public/heartbeat/_global.json` in single-island and we keep it there in multi-island too by reading/writing with `island_id=None`. We do not duplicate the global config per-island in v1 — Phase 3 (migration) won't need that either.

Actually re-check: the spec §4.1 lists heartbeat under "per-island". Re-evaluate: in multi-island mode, do we want one global `consolidate` action across all islands, or per-island? The spec's behavior is per-island because the cadence reads the per-island `eval_count`. So yes, per-island. Write/read with `island_id=island_id` for global too.

Final heartbeat seeding pattern in multi-island: each island has its own `_global.json`. Update the seed in `start_all`:

```python
        if self.config.islands.count > 1:
            for island_id in {s.island_id for s in self.specs if s.island_id is not None}:
                if not read_global_heartbeat(self.paths.coral_dir, island_id=island_id):
                    write_global_heartbeat(
                        self.paths.coral_dir,
                        default_global_actions(self.config),
                        island_id=island_id,
                    )
        else:
            if not read_global_heartbeat(self.paths.coral_dir):
                write_global_heartbeat(self.paths.coral_dir, default_global_actions(self.config))
```

And in `_get_heartbeat_runner`, look up the global config from the agent's island:

```python
        global_actions = read_global_heartbeat(self.paths.coral_dir, island_id=island_id)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/test_manager_seen_attempts.py -v
```

Expected: PASS.

- [ ] **Step 5: Run the full manager + heartbeat test suite**

```bash
uv run pytest tests/test_manager_reliability.py tests/test_manager_seen_attempts.py tests/test_heartbeat.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add coral/agent/manager.py tests/test_manager_seen_attempts.py
git commit -m "feat(manager): monitor loop scans every island's attempts and reads island-scoped heartbeat"
```

---

## Verification before declaring Phase 2 complete

After all tasks land:

```bash
cd /Users/pingu/posttrain/projects/has/CORAL/.claude/worktrees/feat+multi-island
uv run pytest tests/ -q
uv run ruff check .
```

Expected:
- All tests PASS (the original 327 from Phase 1 + ~30 new Phase 2 tests, roughly 355-360 total).
- Ruff reports no new issues.

Manual smoke test:

```bash
# Re-run the existing txn_scheduling task with islands.count=2 and verify the
# directory layout now actually shows islands/0/ and islands/1/ subtrees.
uv run coral start -c examples/ADRS/txn_scheduling/task.yaml islands.count=2 agents.count=4
```

Expected:
- `results/<task>/<ts>/.coral/islands/0/` and `.coral/islands/1/` exist
- `agents/0-agent-1/`, `agents/0-agent-2/`, `agents/1-agent-1/`, `agents/1-agent-2/` exist
- Each agent's worktree has a `.coral_island` breadcrumb
- Each agent's `.claude/notes/` resolves to its island's notes dir
- After agents commit, attempts land in `islands/<id>/attempts/`
- The grader daemon picks them up and writes scores back to the right island

## What Phase 2 ships

- `partition_into_islands` distributes agents round-robin and rewrites IDs with birth-island prefixes.
- `create_project` builds the per-island subtree layout when `islands.count > 1`.
- `setup_shared_state` writes the `.coral_island` breadcrumb and points symlinks at the right island root.
- All four runtime settings writers scope their permissions to the agent's island.
- `_setup_and_start_agent` threads `island_id` end-to-end.
- `submit_eval` reads the breadcrumb and writes attempts into the right island.
- The grader daemon discovers attempts across every island and routes scores back to the right one.
- The manager's monitor loop, heartbeat reads, and eval counter are all island-aware.
- `generate_coral_md` tells each agent which island it lives on.

After Phase 2, multi-island runs work end-to-end except for migration itself (Phase 3 = migration cycle). Agents on different islands evolve in parallel with completely independent shared state.

## What's still in Phases 3 + 4

- **Phase 3 (migration cycle):** the `coral/agent/migration.py` module, `select_candidate`, `copy_agent_contribution`, the `AgentManager._run_migration_cycle` orchestration, the `.coral/migration_log.jsonl`, the `migration_in_progress` marker, and the heartbeat-style neighbor notifications.
- **Phase 4 (CLI/UI surface):** `--island` flag on `coral log` / `coral show` / `coral notes` / `coral skills`, per-island sections in `coral status`, and the migration-history panel in the web UI.

Phase 5 (knockout-and-respawn) remains deferred to a v2 spec.
