# Multi-Island Phase 1 — Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land all the plumbing needed to support multiple per-island shared-state subtrees, without yet activating multi-island behavior at runtime. After this plan, `islands.count` defaults to 1 and the existing test suite must still pass unchanged — the only difference is that every hub primitive now accepts an optional `island_id` and a new `island_root()` resolver knows how to map it to a path on disk.

**Architecture:** A single new module `coral/hub/_island.py` resolves the per-island base path. Every hub module gets an optional `island_id` parameter (default `None`) threaded through its read/write functions. Two new filter helpers (`notes_by`, `skills_by`) prepare for migration. The shipped Phase 1 surface change is the config dataclasses, the resolver, the optional parameter on every hub function, two filters, one CLI helper (`coral note new`), and a small audit/prompt update so agents stamp `creator:`.

**Tech Stack:** Python 3.11+, dataclasses, OmegaConf, pytest, hatchling. No new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-31-multi-island-design.md` §4.1–4.3, §5, §6.2.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `coral/config.py` | Modify | Add `IslandsConfig`, `MigrationConfig` dataclasses; wire into `CoralConfig`. |
| `coral/hub/_island.py` | Create | `island_root(coral_dir, island_id)` resolver (the only new module). |
| `coral/hub/attempts.py` | Modify | Add `island_id` parameter (default `None`) on all read/write functions. |
| `coral/hub/notes.py` | Modify | Add `island_id` parameter; add `notes_by(coral_dir, island_id, agent_id)` filter. |
| `coral/hub/skills.py` | Modify | Add `island_id` parameter; add `skills_by(coral_dir, island_id, agent_id)` filter. |
| `coral/hub/heartbeat.py` | Modify | Add `island_id` parameter on all functions. |
| `coral/hub/checkpoint.py` | Modify | Add `island_id` parameter; per-island `.git` location in multi-island. |
| `coral/cli/__init__.py` | Modify | Register new `note` top-level subparser; dispatch to `cmd_note_new`. |
| `coral/cli/query.py` | Modify | Add `cmd_note_new(args)` handler. |
| `coral/hub/prompts/consolidate.md` | Modify | Add one paragraph instructing `creator:` stamping on new notes. |
| `coral/template/agents/librarian.md` | Modify | Add one paragraph instructing `creator:` stamping on notes the librarian writes. |
| `tests/test_config.py` | Modify | Test `IslandsConfig` defaults and validation. |
| `tests/test_islands.py` | Create | Test `island_root` resolver + multi-island hub round-trip. |
| `tests/test_hub.py` | Modify | Add tests for `notes_by`, `skills_by`. Existing tests are the regression gate. |
| `tests/test_cli_note_new.py` | Create | Test `coral note new <slug>` round-trip. |

---

## Task 1: IslandsConfig and MigrationConfig dataclasses

**Files:**
- Modify: `coral/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for IslandsConfig defaults and validation**

Append to `tests/test_config.py`:

```python
def test_islands_defaults_single_island():
    cfg = CoralConfig.from_dict({
        "task": {"name": "t", "description": "d"},
    })
    assert cfg.islands.count == 1
    assert cfg.islands.migration.enabled is True
    assert cfg.islands.migration.every == 50
    assert cfg.islands.migration.rank_window == 20
    assert cfg.islands.migration.min_evals == 3
    assert cfg.islands.migration.dest_weighting == "score"
    assert cfg.islands.migration.max_per_cycle == 1
    assert cfg.islands.migration.notify_island is True


def test_islands_count_override():
    cfg = CoralConfig.from_dict({
        "task": {"name": "t", "description": "d"},
        "islands": {"count": 4},
    })
    assert cfg.islands.count == 4


def test_islands_migration_override():
    cfg = CoralConfig.from_dict({
        "task": {"name": "t", "description": "d"},
        "islands": {"count": 2, "migration": {"every": 25, "dest_weighting": "uniform"}},
    })
    assert cfg.islands.migration.every == 25
    assert cfg.islands.migration.dest_weighting == "uniform"


def test_islands_count_validation():
    import pytest
    with pytest.raises(ValueError, match="islands.count must be >= 1"):
        CoralConfig.from_dict({
            "task": {"name": "t", "description": "d"},
            "islands": {"count": 0},
        })


def test_migration_every_validation():
    import pytest
    with pytest.raises(ValueError, match="islands.migration.every must be >= 1"):
        CoralConfig.from_dict({
            "task": {"name": "t", "description": "d"},
            "islands": {"migration": {"every": 0}},
        })


def test_migration_rank_window_validation():
    import pytest
    with pytest.raises(ValueError, match="islands.migration.rank_window"):
        CoralConfig.from_dict({
            "task": {"name": "t", "description": "d"},
            "islands": {"migration": {"every": 10, "rank_window": 20}},
        })


def test_migration_dest_weighting_validation():
    import pytest
    with pytest.raises(ValueError, match="dest_weighting"):
        CoralConfig.from_dict({
            "task": {"name": "t", "description": "d"},
            "islands": {"migration": {"dest_weighting": "nonsense"}},
        })
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/test_config.py::test_islands_defaults_single_island -v
```

Expected: FAIL — `AttributeError: 'CoralConfig' object has no attribute 'islands'`

- [ ] **Step 3: Add the dataclasses to `coral/config.py`**

Add immediately above the `@dataclass class CoralConfig` declaration:

```python
@dataclass
class MigrationConfig:
    """Agent migration between islands.

    Ignored in single-island mode (``islands.count == 1``).
    """

    enabled: bool = True
    every: int = 50  # global evals between migration cycles
    rank_window: int = 20  # "best agent" judged by max-over-last-N evals
    min_evals: int = 3  # candidate must have >= N attempts to be eligible
    dest_weighting: str = "score"  # score | uniform | round_robin
    max_per_cycle: int = 1
    notify_island: bool = True

    def __post_init__(self) -> None:
        if self.every < 1:
            raise ValueError(f"islands.migration.every must be >= 1, got {self.every}")
        if self.rank_window < 1:
            raise ValueError(
                f"islands.migration.rank_window must be >= 1, got {self.rank_window}"
            )
        if self.rank_window > self.every:
            raise ValueError(
                f"islands.migration.rank_window ({self.rank_window}) must be "
                f"<= islands.migration.every ({self.every})"
            )
        if self.min_evals < 1:
            raise ValueError(
                f"islands.migration.min_evals must be >= 1, got {self.min_evals}"
            )
        if self.dest_weighting not in {"score", "uniform", "round_robin"}:
            raise ValueError(
                "islands.migration.dest_weighting must be one of "
                f"{{score, uniform, round_robin}}, got {self.dest_weighting!r}"
            )
        if self.max_per_cycle < 1:
            raise ValueError(
                f"islands.migration.max_per_cycle must be >= 1, got {self.max_per_cycle}"
            )


@dataclass
class IslandsConfig:
    """Multi-island shared-state partitioning.

    ``count = 1`` (the default) preserves today's single-island layout exactly
    — no ``.coral/islands/`` directory is created and no migration code paths
    are exercised.
    """

    count: int = 1
    migration: MigrationConfig = field(default_factory=MigrationConfig)

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError(f"islands.count must be >= 1, got {self.count}")
        # OmegaConf round-trip can leave migration as a dict
        if isinstance(self.migration, dict):
            self.migration = MigrationConfig(**self.migration)
```

Then add `islands: IslandsConfig = field(default_factory=IslandsConfig)` to `CoralConfig` (place it after `agents` and before `sharing`).

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v -k islands
```

Expected: PASS (7 new tests).

- [ ] **Step 5: Run the full config test suite to confirm no regression**

```bash
uv run pytest tests/test_config.py -v
```

Expected: all pre-existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add coral/config.py tests/test_config.py
git commit -m "feat(config): add IslandsConfig and MigrationConfig dataclasses"
```

---

## Task 2: `island_root()` resolver

**Files:**
- Create: `coral/hub/_island.py`
- Create: `tests/test_islands.py`

- [ ] **Step 1: Write the failing tests for `island_root`**

Create `tests/test_islands.py`:

```python
"""Tests for multi-island layout primitives."""

import tempfile
from pathlib import Path

import pytest

from coral.hub._island import island_root


def test_island_root_single_island_no_islands_dir():
    """When .coral/islands/ does not exist, island_root returns public/ regardless of id."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        # No islands/ dir created
        assert island_root(coral_dir, None) == coral_dir / "public"
        # Even with island_id, single-island layout returns public/
        assert island_root(coral_dir, "0") == coral_dir / "public"


def test_island_root_multi_island_with_id():
    """When islands/ exists, island_root returns the per-island subdir."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "islands").mkdir()
        assert island_root(coral_dir, "0") == coral_dir / "islands" / "0"
        assert island_root(coral_dir, "3") == coral_dir / "islands" / "3"
        # Integer ids are stringified
        assert island_root(coral_dir, 2) == coral_dir / "islands" / "2"


def test_island_root_multi_island_requires_id():
    """In multi-island layout, island_id=None is an error."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "islands").mkdir()
        with pytest.raises(ValueError, match="island_id is required"):
            island_root(coral_dir, None)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/test_islands.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'coral.hub._island'`.

- [ ] **Step 3: Create the resolver module**

Write `coral/hub/_island.py`:

```python
"""Per-island base-path resolver.

Single-island runs (no ``.coral/islands/`` subdir) return ``coral_dir/public``
regardless of the ``island_id`` argument — this preserves today's layout
exactly and makes the optional ``island_id`` parameter safe to add to every
hub function without changing behavior.

Multi-island runs (``.coral/islands/`` exists) return
``coral_dir/islands/<island_id>``, and require ``island_id`` to be set.
"""

from __future__ import annotations

from pathlib import Path


def island_root(coral_dir: str | Path, island_id: str | int | None) -> Path:
    """Resolve the per-island base path under ``coral_dir``.

    Returns ``coral_dir/public`` in single-island mode (no ``islands/`` subdir
    on disk, regardless of the ``island_id`` argument). Returns
    ``coral_dir/islands/<island_id>`` in multi-island mode; raises if
    ``island_id`` is None there.
    """
    coral_dir = Path(coral_dir)
    islands_dir = coral_dir / "islands"
    if islands_dir.exists():
        if island_id is None:
            raise ValueError(
                "island_id is required in multi-island runs "
                f"({islands_dir} exists on disk)"
            )
        return islands_dir / str(island_id)
    return coral_dir / "public"
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/test_islands.py -v
```

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add coral/hub/_island.py tests/test_islands.py
git commit -m "feat(hub): add island_root() resolver for multi-island layout"
```

---

## Task 3: Thread `island_id` through `coral/hub/attempts.py`

**Files:**
- Modify: `coral/hub/attempts.py`
- Modify: `tests/test_islands.py`

- [ ] **Step 1: Write failing multi-island round-trip tests for attempts**

Append to `tests/test_islands.py`:

```python
from coral.hub.attempts import (
    get_leaderboard,
    increment_eval_count,
    read_attempts,
    read_eval_count,
    write_attempt,
)
from coral.types import Attempt


def _make_attempt(commit: str, agent: str = "agent-1", score: float = 0.5) -> Attempt:
    return Attempt(
        commit_hash=commit,
        agent_id=agent,
        title="t",
        score=score,
        status="improved",
        parent_hash=None,
        timestamp="2026-05-31T10:00:00Z",
    )


def _make_multi_island(coral_dir: Path, n: int = 2) -> None:
    """Create a multi-island layout with N empty islands."""
    for i in range(n):
        (coral_dir / "islands" / str(i) / "attempts").mkdir(parents=True)


def test_write_attempt_multi_island_writes_to_island_dir():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        _make_multi_island(coral_dir, n=2)
        write_attempt(coral_dir, _make_attempt("aaa"), island_id="0")
        write_attempt(coral_dir, _make_attempt("bbb"), island_id="1")
        assert (coral_dir / "islands" / "0" / "attempts" / "aaa.json").exists()
        assert (coral_dir / "islands" / "1" / "attempts" / "bbb.json").exists()
        # Cross-island isolation: island 0 does not see island 1's attempt
        assert not (coral_dir / "islands" / "0" / "attempts" / "bbb.json").exists()


def test_read_attempts_multi_island_isolation():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        _make_multi_island(coral_dir, n=2)
        write_attempt(coral_dir, _make_attempt("aaa", score=0.8), island_id="0")
        write_attempt(coral_dir, _make_attempt("bbb", score=0.6), island_id="1")
        island0 = read_attempts(coral_dir, island_id="0")
        island1 = read_attempts(coral_dir, island_id="1")
        assert {a.commit_hash for a in island0} == {"aaa"}
        assert {a.commit_hash for a in island1} == {"bbb"}


def test_read_attempts_single_island_default_island_id():
    """Pre-existing behavior: no island_id passed, reads from public/."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        write_attempt(coral_dir, _make_attempt("ccc"))
        # Single-island layout: islands/ does not exist on disk
        assert (coral_dir / "public" / "attempts" / "ccc.json").exists()
        assert {a.commit_hash for a in read_attempts(coral_dir)} == {"ccc"}


def test_eval_count_multi_island_global_and_per_island():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        _make_multi_island(coral_dir, n=2)
        increment_eval_count(coral_dir, island_id="0")
        increment_eval_count(coral_dir, island_id="0")
        increment_eval_count(coral_dir, island_id="1")
        # Per-island counters reflect their own evals
        assert read_eval_count(coral_dir, island_id="0") == 2
        assert read_eval_count(coral_dir, island_id="1") == 1
        # Global counter (island_id=None) was also bumped each time
        assert read_eval_count(coral_dir, island_id=None) == 3
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
uv run pytest tests/test_islands.py -v -k attempt or eval_count
```

Expected: FAIL — `TypeError: write_attempt() got an unexpected keyword argument 'island_id'`.

- [ ] **Step 3: Thread `island_id` through `coral/hub/attempts.py`**

In `coral/hub/attempts.py`, replace the existing `_attempts_dir` helper and update every public function to accept `island_id: str | int | None = None`. Reference implementation for the key changes:

```python
from coral.hub._island import island_root


def _attempts_dir(coral_dir: str | Path, island_id: str | int | None = None) -> Path:
    d = island_root(coral_dir, island_id) / "attempts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_attempt(
    coral_dir: str | Path,
    attempt: Attempt,
    island_id: str | int | None = None,
) -> Path:
    path = _attempts_dir(coral_dir, island_id) / f"{attempt.commit_hash}.json"
    # ... (rest of the body unchanged)
```

Apply the same pattern (`island_id: str | int | None = None` parameter, threaded into `_attempts_dir` calls) to:

- `read_attempt`
- `read_attempts`
- `get_leaderboard`
- `get_agent_attempts`
- `agent_in_grader_queue`
- `count_agent_pending`
- `get_recent`
- `per_agent_class_counts`
- `search_attempts`
- `format_status_summary`

For the eval counters, replace the bodies of `increment_eval_count` and `read_eval_count` with:

```python
def _global_eval_count_path(coral_dir: str | Path) -> Path:
    """Global counter: coral_dir/eval_count in multi-island, public/eval_count in single."""
    coral_dir = Path(coral_dir)
    if (coral_dir / "islands").exists():
        return coral_dir / "eval_count"
    return coral_dir / "public" / "eval_count"


def increment_eval_count(coral_dir: str | Path, island_id: str | int | None = None) -> int:
    """Increment the eval counter(s) and return the new per-scope value.

    When ``island_id`` is provided, increments BOTH the per-island counter
    (at ``islands/<id>/eval_count``) and the global counter (at
    ``coral_dir/eval_count`` in multi-island, ``public/eval_count`` in
    single). Returns the per-island value.

    When ``island_id`` is None, increments only the global counter and
    returns its new value.
    """

    def _bump(p: Path) -> int:
        count = 0
        if p.exists():
            try:
                count = int(p.read_text().strip())
            except ValueError:
                pass
        count += 1
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(count))
        return count

    global_path = _global_eval_count_path(coral_dir)
    global_count = _bump(global_path)
    if island_id is None:
        return global_count
    return _bump(island_root(coral_dir, island_id) / "eval_count")


def read_eval_count(coral_dir: str | Path, island_id: str | int | None = None) -> int:
    if island_id is None:
        path = _global_eval_count_path(coral_dir)
    else:
        path = island_root(coral_dir, island_id) / "eval_count"
    if not path.exists():
        return 0
    try:
        return int(path.read_text().strip())
    except ValueError:
        return 0
```

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
uv run pytest tests/test_islands.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run the existing hub tests to confirm no regression**

```bash
uv run pytest tests/test_hub.py -v
```

Expected: all pre-existing tests still PASS (single-island default preserved).

- [ ] **Step 6: Commit**

```bash
git add coral/hub/attempts.py tests/test_islands.py
git commit -m "feat(hub): thread island_id through attempts module"
```

---

## Task 4: Thread `island_id` through `coral/hub/notes.py` + `notes_by` filter

**Files:**
- Modify: `coral/hub/notes.py`
- Modify: `tests/test_islands.py`
- Modify: `tests/test_hub.py`

- [ ] **Step 1: Write failing tests for multi-island notes and `notes_by`**

Append to `tests/test_islands.py`:

```python
from coral.hub.notes import list_notes, notes_by


def test_list_notes_multi_island_isolation():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        for i in range(2):
            (coral_dir / "islands" / str(i) / "notes").mkdir(parents=True)
        (coral_dir / "islands" / "0" / "notes" / "a.md").write_text(
            "---\ncreator: agent-1\ncreated: 2026-05-31\n---\n# A\nbody A\n"
        )
        (coral_dir / "islands" / "1" / "notes" / "b.md").write_text(
            "---\ncreator: agent-2\ncreated: 2026-05-31\n---\n# B\nbody B\n"
        )
        names0 = {e["filename"] for e in list_notes(coral_dir, island_id="0")}
        names1 = {e["filename"] for e in list_notes(coral_dir, island_id="1")}
        assert names0 == {"a.md"}
        assert names1 == {"b.md"}


def test_notes_by_returns_creator_matched_paths():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "islands" / "0" / "notes").mkdir(parents=True)
        notes = coral_dir / "islands" / "0" / "notes"
        (notes / "by-agent-1.md").write_text("---\ncreator: agent-1\n---\nbody\n")
        (notes / "by-agent-2.md").write_text("---\ncreator: agent-2\n---\nbody\n")
        (notes / "anonymous.md").write_text("# no frontmatter\nbody\n")
        matched = notes_by(coral_dir, island_id="0", agent_id="agent-1")
        assert [p.name for p in matched] == ["by-agent-1.md"]
        # The anonymous note (no creator) is excluded
        all_matched = (
            notes_by(coral_dir, island_id="0", agent_id="agent-1")
            + notes_by(coral_dir, island_id="0", agent_id="agent-2")
        )
        assert "anonymous.md" not in {p.name for p in all_matched}


def test_notes_by_single_island_uses_public():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        notes = coral_dir / "public" / "notes"
        notes.mkdir(parents=True)
        (notes / "n.md").write_text("---\ncreator: agent-1\n---\nbody\n")
        matched = notes_by(coral_dir, island_id=None, agent_id="agent-1")
        assert [p.name for p in matched] == ["n.md"]
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
uv run pytest tests/test_islands.py -v -k notes
```

Expected: FAIL — `TypeError: list_notes() got an unexpected keyword argument 'island_id'` (or `notes_by` import error).

- [ ] **Step 3: Thread `island_id` through `coral/hub/notes.py` and add `notes_by`**

In `coral/hub/notes.py`, update `_notes_dir` to use `island_root`, add `island_id` to public functions, and add `notes_by`:

```python
from coral.hub._island import island_root


def _notes_dir(coral_dir: str | Path, island_id: str | int | None = None) -> Path:
    p = island_root(coral_dir, island_id) / "notes"
    p.mkdir(parents=True, exist_ok=True)
    return p
```

Add `island_id: str | int | None = None` parameter to:

- `list_notes`
- `search_notes`
- `get_recent_notes`
- `read_note`
- `read_all_notes`

Threading is mechanical — replace each `_notes_dir(coral_dir)` call with `_notes_dir(coral_dir, island_id)`, and add `island_id` to `list_notes(...)` call sites inside the module. Inside `list_notes`, the legacy `insights/` fallback path also needs island awareness:

```python
def list_notes(
    coral_dir: str | Path,
    island_id: str | int | None = None,
) -> list[dict[str, Any]]:
    notes_dir = _notes_dir(coral_dir, island_id)
    entries = _collect_from_dir(notes_dir)

    insights_dir = island_root(coral_dir, island_id) / "insights"
    if insights_dir.is_dir():
        seen = {e["filename"] for e in entries}
        for e in _collect_from_dir(insights_dir):
            if e["filename"] not in seen:
                entries.append(e)

    # ... (rest of body unchanged)
```

Then append `notes_by`:

```python
def notes_by(
    coral_dir: str | Path,
    island_id: str | int | None,
    agent_id: str,
) -> list[Path]:
    """Return absolute paths of notes whose frontmatter `creator` matches agent_id.

    Notes without a `creator:` field (e.g. legacy notes, the bundled
    notes.md) are excluded — they cannot be safely attributed and should
    stay on the source island when their author migrates.
    """
    notes_dir = _notes_dir(coral_dir, island_id)
    matched: list[Path] = []
    for md_file in sorted(notes_dir.rglob("*.md")):
        if md_file.name == "notes.md" or md_file.name.startswith("_"):
            continue
        meta, _ = _parse_frontmatter(md_file.read_text())
        if meta.get("creator") == agent_id:
            matched.append(md_file)
    return matched
```

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
uv run pytest tests/test_islands.py -v -k notes
```

Expected: PASS.

- [ ] **Step 5: Run pre-existing notes tests to confirm no regression**

```bash
uv run pytest tests/test_hub.py -v -k note
```

Expected: all pre-existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add coral/hub/notes.py tests/test_islands.py
git commit -m "feat(hub): thread island_id through notes and add notes_by filter"
```

---

## Task 5: Thread `island_id` through `coral/hub/skills.py` + `skills_by` filter

**Files:**
- Modify: `coral/hub/skills.py`
- Modify: `tests/test_islands.py`

- [ ] **Step 1: Write failing tests for multi-island skills and `skills_by`**

Append to `tests/test_islands.py`:

```python
from coral.hub.skills import list_skills, skills_by


def _write_skill(dir_: Path, name: str, creator: str | None) -> None:
    """Helper: create a skill dir with SKILL.md, optionally stamped with `creator:`."""
    sk_dir = dir_ / name
    sk_dir.mkdir(parents=True)
    if creator is None:
        sk_dir.joinpath("SKILL.md").write_text(
            f"---\nname: {name}\ndescription: test skill\n---\nbody\n"
        )
    else:
        sk_dir.joinpath("SKILL.md").write_text(
            f"---\nname: {name}\ndescription: test skill\ncreator: {creator}\n---\nbody\n"
        )


def test_list_skills_multi_island_isolation():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        for i in range(2):
            (coral_dir / "islands" / str(i) / "skills").mkdir(parents=True)
        _write_skill(coral_dir / "islands" / "0" / "skills", "alpha", creator="agent-1")
        _write_skill(coral_dir / "islands" / "1" / "skills", "beta", creator="agent-2")
        names0 = {s["name"] for s in list_skills(coral_dir, island_id="0")}
        names1 = {s["name"] for s in list_skills(coral_dir, island_id="1")}
        assert names0 == {"alpha"}
        assert names1 == {"beta"}


def test_skills_by_excludes_bundled_unstamped_skills():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        skills_dir = coral_dir / "islands" / "0" / "skills"
        skills_dir.mkdir(parents=True)
        _write_skill(skills_dir, "agent-built", creator="agent-1")
        _write_skill(skills_dir, "bundled", creator=None)
        matched = skills_by(coral_dir, island_id="0", agent_id="agent-1")
        assert [p.name for p in matched] == ["agent-built"]


def test_skills_by_single_island_uses_public():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        skills_dir = coral_dir / "public" / "skills"
        skills_dir.mkdir(parents=True)
        _write_skill(skills_dir, "mine", creator="agent-7")
        matched = skills_by(coral_dir, island_id=None, agent_id="agent-7")
        assert [p.name for p in matched] == ["mine"]
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
uv run pytest tests/test_islands.py -v -k skill
```

Expected: FAIL — `TypeError: list_skills() got an unexpected keyword argument 'island_id'`.

- [ ] **Step 3: Thread `island_id` through `coral/hub/skills.py` and add `skills_by`**

In `coral/hub/skills.py`, update `_skills_dir` to use `island_root`, add `island_id` parameter to public functions, and add `skills_by`:

```python
from coral.hub._island import island_root


def _skills_dir(coral_dir: str | Path, island_id: str | int | None = None) -> Path:
    d = island_root(coral_dir, island_id) / "skills"
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_skills(
    coral_dir: str | Path,
    island_id: str | int | None = None,
) -> list[dict[str, Any]]:
    # ... existing body with _skills_dir(coral_dir, island_id)
```

Then append:

```python
def skills_by(
    coral_dir: str | Path,
    island_id: str | int | None,
    agent_id: str,
) -> list[Path]:
    """Return absolute paths of skill directories whose SKILL.md frontmatter
    `creator` matches agent_id.

    Skills without a `creator:` field are treated as bundled-framework skills
    (deep-research, librarian, skill-creator, organize-files) and excluded —
    they are seeded per-island already and should not migrate.
    """
    skills_dir = _skills_dir(coral_dir, island_id)
    matched: list[Path] = []
    for sk_dir in sorted(skills_dir.iterdir()):
        if not sk_dir.is_dir():
            continue
        skill_md = sk_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        meta, _ = _parse_frontmatter(skill_md.read_text())
        if meta.get("creator") == agent_id:
            matched.append(sk_dir)
    return matched
```

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
uv run pytest tests/test_islands.py -v -k skill
```

Expected: PASS.

- [ ] **Step 5: Run pre-existing hub tests to confirm no regression**

```bash
uv run pytest tests/test_hub.py -v -k skill
```

Expected: all pre-existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add coral/hub/skills.py tests/test_islands.py
git commit -m "feat(hub): thread island_id through skills and add skills_by filter"
```

---

## Task 6: Thread `island_id` through `coral/hub/heartbeat.py`

**Files:**
- Modify: `coral/hub/heartbeat.py`
- Modify: `tests/test_islands.py`

- [ ] **Step 1: Write failing tests for multi-island heartbeat config**

Append to `tests/test_islands.py`:

```python
from coral.hub.heartbeat import (
    read_agent_heartbeat,
    read_global_heartbeat,
    write_agent_heartbeat,
    write_global_heartbeat,
)


def test_heartbeat_multi_island_isolation():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        for i in range(2):
            (coral_dir / "islands" / str(i) / "heartbeat").mkdir(parents=True)
        write_agent_heartbeat(
            coral_dir,
            "agent-1",
            [{"name": "reflect", "every": 1, "prompt": "island-0 reflect"}],
            island_id="0",
        )
        write_agent_heartbeat(
            coral_dir,
            "agent-1",
            [{"name": "reflect", "every": 2, "prompt": "island-1 reflect"}],
            island_id="1",
        )
        a0 = read_agent_heartbeat(coral_dir, "agent-1", island_id="0")
        a1 = read_agent_heartbeat(coral_dir, "agent-1", island_id="1")
        assert next(a for a in a0 if a["name"] == "reflect")["every"] == 1
        assert next(a for a in a1 if a["name"] == "reflect")["every"] == 2


def test_global_heartbeat_multi_island_isolation():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        for i in range(2):
            (coral_dir / "islands" / str(i) / "heartbeat").mkdir(parents=True)
        write_global_heartbeat(
            coral_dir, [{"name": "consolidate", "every": 10}], island_id="0"
        )
        write_global_heartbeat(
            coral_dir, [{"name": "consolidate", "every": 20}], island_id="1"
        )
        g0 = read_global_heartbeat(coral_dir, island_id="0")
        g1 = read_global_heartbeat(coral_dir, island_id="1")
        assert next(a for a in g0 if a["name"] == "consolidate")["every"] == 10
        assert next(a for a in g1 if a["name"] == "consolidate")["every"] == 20
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
uv run pytest tests/test_islands.py -v -k heartbeat
```

Expected: FAIL — `TypeError: write_agent_heartbeat() got an unexpected keyword argument 'island_id'`.

- [ ] **Step 3: Thread `island_id` through `coral/hub/heartbeat.py`**

In `coral/hub/heartbeat.py`, update `_heartbeat_path` and the four public CRUD functions:

```python
from coral.hub._island import island_root


def _heartbeat_path(
    coral_dir: Path,
    agent_id: str,
    island_id: str | int | None = None,
) -> Path:
    return island_root(coral_dir, island_id) / "heartbeat" / f"{agent_id}.json"


def read_agent_heartbeat(
    coral_dir: Path,
    agent_id: str,
    island_id: str | int | None = None,
) -> list[dict]:
    return _read_actions(_heartbeat_path(coral_dir, agent_id, island_id))


def write_agent_heartbeat(
    coral_dir: Path,
    agent_id: str,
    actions: list[dict],
    island_id: str | int | None = None,
) -> None:
    # ... existing protected-action logic ...
    _write_actions(_heartbeat_path(coral_dir, agent_id, island_id), actions)


def read_global_heartbeat(
    coral_dir: Path,
    island_id: str | int | None = None,
) -> list[dict]:
    return _read_actions(_heartbeat_path(coral_dir, _GLOBAL_ID, island_id))


def write_global_heartbeat(
    coral_dir: Path,
    actions: list[dict],
    island_id: str | int | None = None,
) -> None:
    # ... existing protected-action logic ...
    _write_actions(_heartbeat_path(coral_dir, _GLOBAL_ID, island_id), actions)
```

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
uv run pytest tests/test_islands.py -v -k heartbeat
```

Expected: PASS.

- [ ] **Step 5: Run pre-existing heartbeat tests to confirm no regression**

```bash
uv run pytest tests/test_heartbeat.py -v
```

Expected: all pre-existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add coral/hub/heartbeat.py tests/test_islands.py
git commit -m "feat(hub): thread island_id through heartbeat module"
```

---

## Task 7: Thread `island_id` through `coral/hub/checkpoint.py`

**Files:**
- Modify: `coral/hub/checkpoint.py`
- Modify: `tests/test_islands.py`

The checkpoint module is trickier than the others because it manages a git repo whose `.git` directory location differs between modes:

- Single-island: `.git` at `coral_dir/public/.git` (today's behavior).
- Multi-island: `.git` at `coral_dir/islands/<id>/.git`.

Each island gets its own checkpoint repo — checkpoint locks stay scoped per-island.

- [ ] **Step 1: Write failing tests for multi-island checkpoint isolation**

Append to `tests/test_islands.py`:

```python
import subprocess

from coral.hub.checkpoint import (
    checkpoint,
    checkpoint_history,
    init_checkpoint_repo,
)


def test_checkpoint_multi_island_separate_repos():
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        for i in range(2):
            (coral_dir / "islands" / str(i) / "notes").mkdir(parents=True)
        init_checkpoint_repo(str(coral_dir), island_id="0")
        init_checkpoint_repo(str(coral_dir), island_id="1")

        # Distinct .git dirs per island
        assert (coral_dir / "islands" / "0" / ".git").is_dir()
        assert (coral_dir / "islands" / "1" / ".git").is_dir()

        # Write a note on island 0, checkpoint it
        (coral_dir / "islands" / "0" / "notes" / "a.md").write_text("hello island 0")
        h0 = checkpoint(str(coral_dir), "agent-1", "note on island 0", island_id="0")
        assert h0 is not None

        # Island 1 does not see island 0's commit
        h1_history = checkpoint_history(str(coral_dir), island_id="1")
        assert all("island 0" not in entry["message"] for entry in h1_history)


def test_checkpoint_single_island_default_unchanged():
    """Regression: existing single-island callers (no island_id) still use public/.git."""
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d)
        (coral_dir / "public" / "notes").mkdir(parents=True)
        init_checkpoint_repo(str(coral_dir))
        assert (coral_dir / "public" / ".git").is_dir()
        (coral_dir / "public" / "notes" / "a.md").write_text("hello")
        h = checkpoint(str(coral_dir), "agent-1", "first note")
        assert h is not None
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
uv run pytest tests/test_islands.py -v -k checkpoint
```

Expected: FAIL on the multi-island test — `TypeError: init_checkpoint_repo() got an unexpected keyword argument 'island_id'`.

- [ ] **Step 3: Thread `island_id` through `coral/hub/checkpoint.py`**

Replace `_public_dir` with `_checkpoint_dir` that uses `island_root`, and add `island_id` to all public functions:

```python
from coral.hub._island import island_root


def _checkpoint_dir(coral_dir: str, island_id: str | int | None = None) -> Path:
    """The directory the checkpoint repo lives in (public/ or islands/<id>/)."""
    return island_root(coral_dir, island_id)


def init_checkpoint_repo(coral_dir: str, island_id: str | int | None = None) -> None:
    """Initialize a git repo inside the island root for shared state tracking."""
    root = _checkpoint_dir(coral_dir, island_id)
    root.mkdir(parents=True, exist_ok=True)
    if (root / ".git").exists():
        return
    # ... (rest of body unchanged, using `root` in place of `public`)


def checkpoint(
    coral_dir: str,
    agent_id: str,
    message: str,
    island_id: str | int | None = None,
) -> str | None:
    root = _checkpoint_dir(coral_dir, island_id)
    if not (root / ".git").exists():
        init_checkpoint_repo(coral_dir, island_id)
    lock_path = root / ".git" / "coral.lock"
    # ... (rest of body unchanged, using `root` in place of `public`)


def checkpoint_history(
    coral_dir: str,
    count: int = 20,
    island_id: str | int | None = None,
) -> list[dict[str, str]]:
    root = _checkpoint_dir(coral_dir, island_id)
    if not (root / ".git").exists():
        return []
    # ... (rest of body unchanged, using `root` in place of `public`)


def checkpoint_diff(
    coral_dir: str,
    commit_hash: str,
    island_id: str | int | None = None,
) -> str:
    root = _checkpoint_dir(coral_dir, island_id)
    if not (root / ".git").exists():
        return "No checkpoint repo found."
    # ... (rest of body unchanged, using `root` in place of `public`)
```

The bodies are pure search-replace `public` → `root`. Keep all `subprocess.run` calls' `cwd=str(root)` and the lock path computation.

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
uv run pytest tests/test_islands.py -v -k checkpoint
```

Expected: PASS.

- [ ] **Step 5: Run pre-existing checkpoint tests to confirm no regression**

```bash
uv run pytest tests/test_checkpoint.py -v
```

Expected: all pre-existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add coral/hub/checkpoint.py tests/test_islands.py
git commit -m "feat(hub): thread island_id through checkpoint module"
```

---

## Task 8: Audit bundled `SKILL.md` and update creator-stamping prompts

This task has two parts: a defensive audit (delete any stray `creator:` from bundled skill frontmatter so `skills_by` filters them out), and a prompt nudge (so agents stamp `creator:` on the notes and skills they author).

**Files:**
- Modify: `coral/template/skills/*/SKILL.md` (audit; only edit if a `creator:` field exists in frontmatter)
- Modify: `coral/hub/prompts/consolidate.md`
- Modify: `coral/template/agents/librarian.md`
- Modify: `coral/template/skills/skill-creator/SKILL.md`
- Create: `tests/test_creator_stamping.py`

- [ ] **Step 1: Inspect bundled SKILL.md frontmatter for stray `creator:` fields**

```bash
grep -l "^creator:" coral/template/skills/*/SKILL.md 2>/dev/null
```

Expected: no output (a quick `grep -rn "creator:" coral/template/skills/` earlier in recon showed `creator:` only appears in *bodies* / reference templates / scripts, never in SKILL.md frontmatter — but verify before continuing). If any SKILL.md frontmatter contains `creator:`, delete that line so the skill is treated as bundled.

- [ ] **Step 2: Write the failing prompt-content test**

Create `tests/test_creator_stamping.py`:

```python
"""Bundled prompts and subagent templates instruct agents to stamp `creator:`.

Migration filters notes/skills by frontmatter `creator: <agent_id>`. If the
canonical heartbeat prompt and the bundled subagent / skill-creator templates
do not tell agents to stamp it, migration will silently drop their work.
This test is the regression gate for that instruction surviving future
prompt edits.
"""

from pathlib import Path


COMMON_INSTRUCTION_KEYWORDS = ["creator:", "frontmatter"]


def _check_prompt(path: Path) -> None:
    text = path.read_text().lower()
    for kw in COMMON_INSTRUCTION_KEYWORDS:
        assert kw in text, f"{path} must mention {kw!r} so agents stamp the creator field"


def test_consolidate_prompt_instructs_creator_stamping():
    _check_prompt(Path("coral/hub/prompts/consolidate.md"))


def test_librarian_template_instructs_creator_stamping():
    _check_prompt(Path("coral/template/agents/librarian.md"))


def test_skill_creator_template_instructs_creator_stamping():
    _check_prompt(Path("coral/template/skills/skill-creator/SKILL.md"))


def test_bundled_skill_md_files_have_no_creator_frontmatter():
    """Bundled skills must not have `creator:` in their SKILL.md frontmatter, so
    migration's `skills_by` filter correctly excludes them."""
    bundled = Path("coral/template/skills").rglob("SKILL.md")
    for skill_md in bundled:
        text = skill_md.read_text()
        # Only inspect frontmatter (first --- block); body may legitimately mention "creator"
        if not text.startswith("---"):
            continue
        end = text.find("---", 3)
        front = text[3:end]
        assert "\ncreator:" not in front and not front.startswith("creator:"), (
            f"{skill_md} has stray `creator:` in frontmatter — would migrate as agent-authored"
        )
```

- [ ] **Step 3: Run the new tests to verify they fail**

```bash
uv run pytest tests/test_creator_stamping.py -v
```

Expected: prompt tests FAIL (consolidate.md, librarian.md, skill-creator/SKILL.md do not currently mention `creator:` AND `frontmatter` together); skill-md audit test PASSes (audit was clean).

- [ ] **Step 4: Add a creator-stamping paragraph to `coral/hub/prompts/consolidate.md`**

Append the following paragraph just before the final line (`After consolidating, resume optimizing.`):

```
### Stamp authorship on every new note

When you create a new note (synthesis, connections map, open-questions list,
or anything under `notes/`), include `creator:` in the YAML frontmatter so
the file is attributed to you. Use your own `agent_id` (read from
`.coral_agent_id` if you don't already know it) and an ISO-8601 `created:`
timestamp. Example:

```
---
creator: {agent_id}
created: 2026-05-31T14:32:00Z
---
# Synthesis: ...
```

Notes without a `creator:` field cannot be attributed and will be skipped by
team-level processes that filter by author (skill discovery, migration).
```

(The double backtick-fence inside the prompt is fine — the prompt is markdown that the agent reads, the inner fence is part of the example.)

- [ ] **Step 5: Add the same instruction to `coral/template/agents/librarian.md`**

Append to the librarian template (before the closing line of instructions):

```
## Frontmatter discipline

Every note you create or rewrite must include `creator:` and `created:` in
the YAML frontmatter. Use the agent_id read from `.coral_agent_id`. Notes
without a `creator:` cannot be attributed and will be filtered out of
team-level views.
```

- [ ] **Step 6: Add a skill-frontmatter discipline section to `coral/template/skills/skill-creator/SKILL.md`**

Append at the end of `coral/template/skills/skill-creator/SKILL.md`:

```
## Frontmatter discipline (required)

When you package a new skill, the SKILL.md frontmatter MUST include
`creator:` set to your `agent_id` (read from `.coral_agent_id`). Example:

```
---
name: my-new-skill
description: ...
creator: 0-agent-2
---
```

Skills without `creator:` are treated as bundled framework skills (the
deep-research, librarian, organize-files, skill-creator set seeded into
every island), and team-level processes that filter by author (migration,
provenance UI) will silently exclude them. Always stamp `creator:` on
agent-authored skills.
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
uv run pytest tests/test_creator_stamping.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add tests/test_creator_stamping.py coral/hub/prompts/consolidate.md coral/template/agents/librarian.md coral/template/skills/skill-creator/SKILL.md
git commit -m "feat(prompts): instruct agents to stamp creator on notes and skills"
```

---

## Task 9: `coral note new <slug>` CLI helper

A small helper that pre-stamps `creator:` and `created:` on a fresh note. Saves the body from stdin (or `--body` for short bodies).

**Files:**
- Modify: `coral/cli/__init__.py` (register `note` subparser, dispatch)
- Modify: `coral/cli/query.py` (add `cmd_note_new` handler)
- Create: `tests/test_cli_note_new.py`

- [ ] **Step 1: Write the failing CLI test**

Create `tests/test_cli_note_new.py`:

```python
"""End-to-end test for `coral note new <slug>`."""

import os
import subprocess
import tempfile
from pathlib import Path


def test_note_new_stamps_creator_and_created(tmp_path):
    """`coral note new <slug>` writes a note with `creator:` + `created:` stamped."""
    coral_dir = tmp_path / ".coral"
    (coral_dir / "public" / "notes").mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    # Single-island breadcrumbs
    (worktree / ".coral_dir").write_text(str(coral_dir.resolve()))
    (worktree / ".coral_agent_id").write_text("agent-7")

    env = os.environ.copy()
    result = subprocess.run(
        ["coral", "note", "new", "my-finding", "--body", "First-line summary."],
        cwd=str(worktree),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    note_path = coral_dir / "public" / "notes" / "my-finding.md"
    assert note_path.exists()
    text = note_path.read_text()
    assert text.startswith("---")
    assert "creator: agent-7" in text
    assert "created:" in text
    assert "First-line summary." in text


def test_note_new_writes_to_island_in_multi_island(tmp_path):
    """In multi-island mode, the note lands in islands/<id>/notes/."""
    coral_dir = tmp_path / ".coral"
    (coral_dir / "islands" / "1" / "notes").mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".coral_dir").write_text(str(coral_dir.resolve()))
    (worktree / ".coral_agent_id").write_text("0-agent-2")
    (worktree / ".coral_island").write_text("1")

    env = os.environ.copy()
    result = subprocess.run(
        ["coral", "note", "new", "moved-and-found", "--body", "body"],
        cwd=str(worktree),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    note_path = coral_dir / "islands" / "1" / "notes" / "moved-and-found.md"
    assert note_path.exists()
    assert "creator: 0-agent-2" in note_path.read_text()
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
uv run pytest tests/test_cli_note_new.py -v
```

Expected: FAIL — `coral: error: invalid choice: 'note'`.

- [ ] **Step 3: Add the `cmd_note_new` handler to `coral/cli/query.py`**

Append to `coral/cli/query.py` (or create the function in the most appropriate existing module — query.py is where cmd_notes lives):

```python
def cmd_note_new(args: argparse.Namespace) -> int:
    """Create a new note pre-stamped with `creator:` and `created:` frontmatter."""
    import re
    from datetime import UTC, datetime
    from pathlib import Path

    from coral.hub._island import island_root
    from coral.workspace.worktree import get_coral_dir

    # Resolve coral_dir, agent_id, and island_id from the agent's worktree.
    cwd = Path.cwd()
    coral_dir = get_coral_dir(cwd)
    if coral_dir is None:
        print("error: not in a coral worktree (no .coral_dir breadcrumb found)", file=sys.stderr)
        return 1
    aid_file = cwd / ".coral_agent_id"
    if not aid_file.exists():
        print("error: no .coral_agent_id found in current directory", file=sys.stderr)
        return 1
    agent_id = aid_file.read_text().strip()
    island_file = cwd / ".coral_island"
    island_id = island_file.read_text().strip() if island_file.exists() else None

    # Sanitize slug: a-z0-9-_
    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "-", args.slug).strip("-")
    if not slug:
        print(f"error: slug {args.slug!r} is empty after sanitization", file=sys.stderr)
        return 1

    body = args.body if args.body else sys.stdin.read()

    notes_dir = island_root(coral_dir, island_id) / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    note_path = notes_dir / f"{slug}.md"
    if note_path.exists():
        print(f"error: {note_path} already exists", file=sys.stderr)
        return 1

    created = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    content = (
        "---\n"
        f"creator: {agent_id}\n"
        f"created: {created}\n"
        "---\n"
        f"{body.rstrip()}\n"
    )
    note_path.write_text(content)
    print(str(note_path))
    return 0
```

- [ ] **Step 4: Register the `note` subparser in `coral/cli/__init__.py`**

In `coral/cli/__init__.py`, find the block where `p_notes` is registered (the existing `notes` plural subparser) and add immediately after it:

```python
    p_note = sub.add_parser(
        "note",
        help="Note-authoring helpers (singular)",
        description="Create a new note pre-stamped with creator/created frontmatter.",
        formatter_class=_CommandHelpFormatter,
    )
    note_sub = p_note.add_subparsers(dest="note_cmd", required=True)
    p_note_new = note_sub.add_parser(
        "new",
        help="Create a new note (creator/created stamped)",
        description="Create a new note in the current island with frontmatter stamping.",
    )
    p_note_new.add_argument("slug", help="Slug for the note filename (becomes <slug>.md)")
    p_note_new.add_argument(
        "--body",
        default="",
        help="Note body (use stdin if omitted)",
    )
```

Then add `"note"` to the `_VISIBLE_COMMANDS` list near the top so "did you mean?" suggestions work.

Add the dispatch entry: find the dict that maps command names to functions (around line 536, where `cmd_notes` is registered) and add `"note": cmd_note_new,`. Update the import line just above it to include `cmd_note_new`.

- [ ] **Step 5: Run the new tests to verify they pass**

```bash
uv run pytest tests/test_cli_note_new.py -v
```

Expected: PASS (2 tests).

- [ ] **Step 6: Run the full test suite to confirm no regression**

```bash
uv run pytest tests/ -q
```

Expected: all tests PASS (the original 289 + ~20 new Phase 1 tests).

- [ ] **Step 7: Commit**

```bash
git add coral/cli/__init__.py coral/cli/query.py tests/test_cli_note_new.py
git commit -m "feat(cli): add 'coral note new' helper with creator/created stamping"
```

---

## Verification before declaring Phase 1 complete

After all tasks land, run:

```bash
uv run pytest tests/ -q
uv run ruff check .
```

Expected:

- All tests PASS (original suite + new Phase 1 tests, roughly 310 total).
- Ruff reports no new issues.

If either fails, **do not** mark Phase 1 done — investigate the failure first.

## What Phase 1 ships

- `islands.count`, `islands.migration.*` config knobs exist (single-island default unchanged).
- `island_root()` resolver in `coral/hub/_island.py`.
- Every hub module accepts an optional `island_id` (default `None` = today's behavior).
- `notes_by(coral_dir, island_id, agent_id)` and `skills_by(coral_dir, island_id, agent_id)` filters land migration's attribution surface.
- `coral note new <slug>` helper writes pre-stamped notes.
- Bundled `consolidate.md` and `librarian.md` instruct agents to stamp `creator:`.
- Bundled `SKILL.md` files have been audited; none carry a `creator:` field.

Phase 2 (Island layout in workspace) will use this plumbing to actually create `islands/<id>/` directories at run setup and point per-agent symlinks at the right island.
