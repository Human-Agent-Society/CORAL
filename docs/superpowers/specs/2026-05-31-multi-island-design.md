# Multi-Island CORAL with Agent Migration

**Status:** Implemented v1 design — knockout deferred to follow-up.
**Author:** brainstormed with Claude.
**Scope:** v1 = islands + migration. v2 (TODO) = knockout-and-respawn.

## 1. Goal

Run multiple isolated CORAL "islands" inside a single run. Each island is a self-contained shared-knowledge space (its own attempts, notes, skills, roles); agents on an island only ever read their own island's state, with the same primitives they use today. Periodically, the **best-performing agent on one island migrates** to another island, carrying its agent identity and eval history (role, heartbeat, attempts, eval logs) while notes and skills remain island-local shared knowledge.

The framework's job is selection and bookkeeping. The agents' job is the same as today: read shared state, do work, write shared state. Migration is a manager-side mechanism the agents do not need to understand explicitly.

## 2. Non-goals

- **Knockout-and-respawn** is deferred. v1 ships migration only. The directory layout and config schema are designed so knockout slots in later without a migration.
- **Cross-island reading** by agents during normal work (e.g. `coral log --island 2` from inside island 0). The infrastructure could support it, but it adds another mental model surface and the user prefers selection-only for v1.
- **Migrating notes or skills authored by the agent.** v1 keeps notes and skills on the source island as island-local shared knowledge. Cross-island note/skill copying can be added later if it proves useful.
- **Cross-run migration** (between separate `coral start` invocations). All islands live inside one run.
- **Heterogeneous islands** (different runtimes / models per island). Existing `agents.assignments` mix-and-match remains unchanged; islands are partitions of the resolved agent pool.

## 3. Background

The arxiv reference (2506.13131 — AlphaEvolve) cites "island-based population models" exactly once, pointing at FunSearch [97] for the actual mechanism. In FunSearch, the **individual is a single program**; "migration" is really *island reset* (every M iterations, the worst-half islands are wiped and reseeded from a top island's program clusters). Pure migration — copying individuals between islands without erasing — is the older island-model GA pattern.

CORAL is meaningfully different from FunSearch:

- The "individual" is not just a program. It is an **agent + its mutable role, cadence, attempt history, and runtime context**.
- Knowledge accumulates in the shared `.coral/public/` directory over the lifetime of a run. Wiping that knowledge on a few bad rolls is wasteful in a way it is not in FunSearch.
- Agents read shared state through `coral log`, `coral show`, `coral notes`, `coral skills`, and reading files under `.claude/`. Any new mechanism that does not flow through these primitives is invisible to them.

The design below treats the **live agent identity and eval history** as the migrating unit and routes all visible state through CORAL's existing reading surface.

## 4. Architecture

### 4.1 Directory layout

Multi-island runs (`islands.count > 1`) use a new layout under `.coral/`:

```
run_dir/
├── .coral/
│   ├── public/                       # GLOBAL run state (kept; checkpoint .git moves to per-island)
│   │   ├── grader_daemon.pid
│   │   ├── grader_daemon_heartbeat
│   │   ├── manager.pid
│   │   ├── agent.pids
│   │   ├── agent_pids.json
│   │   ├── agent_state.json
│   │   ├── sessions.json
│   │   ├── diagnostics/<agent_id>/
│   │   └── gateway/
│   ├── private/                      # grader code/venv (global, unchanged)
│   ├── islands/
│   │   └── <island_id>/
│   │       ├── attempts/
│   │       ├── notes/
│   │       ├── skills/               # bundled framework skills are seeded here per-island
│   │       ├── agents/               # bundled subagent templates seeded here per-island
│   │       ├── roles/<agent_id>.md
│   │       ├── heartbeat/<agent_id>.json
│   │       ├── eval_logs/
│   │       ├── logs/
│   │       ├── eval_count            # per-island counter (NEW)
│   │       └── .git                  # per-island checkpoint repo (NEW; see §4.3)
│   ├── eval_count                    # GLOBAL counter (kept for migration cadence)
│   ├── config.yaml
│   └── config_dir
├── repo/                             # cloned source repo, single shared object DB
└── agents/
    └── <agent_id>/                   # worktree on branch coral/<agent_id>; path stable across migration
```

**Per-island vs global**: `attempts`, `notes`, `skills`, `agents` (subagent templates), `roles`, `heartbeat`, `eval_logs`, `logs`, and `eval_count` are *per-island*. The grader daemon, manager state, gateway logs, sessions, and the checkpoint git repo are *global*. Per-agent diagnostics stay global because agent_ids are globally unique (see §4.4).

**Single-island runs (`islands.count == 1`) keep today's exact layout.** No `islands/` directory is created; everything goes under `public/` as before. The hub-module shims described in §4.3 detect single-island layout and elide the `islands/0/` indirection.

### 4.2 Symlink layer in worktrees

Today, `setup_shared_state` creates the agent's runtime shared dir (e.g. `.claude/`) inside the worktree and symlinks subdirs (`attempts`, `notes`, `skills`, `agents`, `roles`, `heartbeat`, `eval_logs`, `logs`) into `.coral/public/`. The new behavior:

- In **single-island** mode, behavior is unchanged — links target `public/`.
- In **multi-island** mode, the same subdirs target `islands/<island_id>/` instead. The agent reads/writes the same paths it reads/writes today; it has no idea it is on an island.

Bundled framework skills (`coral/template/skills/`) and subagent templates (`coral/template/agents/`) are *seeded per-island at run setup* — i.e., copied into each island's `skills/` and `agents/` dir, the same way they are seeded into `public/skills/` and `public/agents/` today. This keeps the agent's view flat: one `skills/` dir containing both bundled and agent-authored skills.

### 4.3 Hub-module shim

The hub modules currently take a `coral_dir` and write to `coral_dir / "public" / ...`. They will switch to `island_root(coral_dir, island_id) / ...`, where:

```python
# coral/hub/_island.py (new)
def island_root(coral_dir: Path, island_id: str | int | None) -> Path:
    """Resolve the per-island base path under coral_dir.

    Single-island runs (no `islands/` subdir) return `coral_dir / 'public'`.
    Multi-island returns `coral_dir / 'islands' / str(island_id)`.
    """
    islands_dir = coral_dir / "islands"
    if islands_dir.exists():
        if island_id is None:
            raise ValueError("island_id is required in multi-island runs")
        return islands_dir / str(island_id)
    return coral_dir / "public"
```

The `island_id` parameter threads through:

- `hub.attempts.{write,read,read_attempts,get_leaderboard,...}`
- `hub.notes.*`
- `hub.skills.*`
- `hub.heartbeat.*`
- `hub.checkpoint.*` — see below.

**Checkpoint repo is per-island in multi-island mode.** Today the checkpoint git repo lives at `.coral/public/.git` and tracks all of `public/`. In multi-island mode, each island gets its own checkpoint repo at `islands/<id>/.git`, tracking only that island's subtree. `init_checkpoint_repo(coral_dir, island_id)` initializes the right one; `checkpoint(coral_dir, island_id, agent_id, message)` commits within the right one. This keeps checkpoint locks scoped to a single island (no cross-island contention) and means a migration's file copies are *not* automatically a single atomic checkpoint — that's fine, migration is rare and the per-island checkpoint after a migration is taken on the destination once the copy completes.

Resolving `island_id` from a worktree:

- `setup_shared_state` writes a new breadcrumb `.coral_island` (alongside the existing `.coral_dir` and `.coral_agent_id`) when running in multi-island mode.
- `coral eval`, `coral log`, etc. read this breadcrumb to determine which island they are operating on.
- In single-island mode, the breadcrumb is absent and `island_id=None` triggers the legacy `public/` path.

### 4.4 Globally-unique agent IDs

Today, agent IDs are `agent-1`, `agent-2`, etc. — flat per run. In multi-island runs we prefix with the **birth island ID**:

```
0-agent-1   # born on island 0, slot 1
0-agent-2   # born on island 0, slot 2
1-agent-1   # born on island 1, slot 1
1-agent-2   # born on island 1, slot 2
```

When `0-agent-2` migrates from island 0 to island 1, it **keeps its `0-agent-2` ID** — the prefix is the *birth-island lineage marker*, not the current location. This makes migration history visible: the existence of `0-agent-2` on island 1's leaderboard is itself the signal that "this agent came from island 0."

v1 does not spawn replacement agents, so no per-island agent-id sequence state is needed after startup.

In single-island mode (`islands.count == 1`), IDs stay `agent-1`, `agent-2`, ... unchanged.

### 4.5 Agent worktrees

Worktree paths are `agents/<agent_id>/` — **no island prefix in the path**. The agent_id already encodes the birth island (`0-agent-2`), and an agent's worktree path is stable across migration (the *contents* and *symlink targets* change, not the path string). Branch names are `coral/<agent_id>` (e.g. `coral/0-agent-2`).

When an agent migrates from island A to island B, the migration cycle:

1. Stops the agent's process.
2. Removes the old worktree via `git worktree remove agents/<agent_id>`.
3. Recreates the worktree at the same path via `git worktree add agents/<agent_id> coral/<agent_id>` — the branch is reused, so the agent's working-tree state on arrival matches their last commit on the source. Their committed code lineage is intact; only the surrounding shared-state symlinks point at a different island.
4. Sets up shared-state symlinks targeting `islands/B/` (instead of `islands/A/`) and writes a fresh `.coral_island = B` breadcrumb.

All worktrees share one cloned `repo/` (one git object database) — so commit hashes resolve from any worktree, and `coral show <hash>` from one island's agent can read a commit produced by another island's agent.

### 4.6 Manager partitioning

`AgentManager` resolves specs into `(island_id, agent_id)` pairs in `start_all`. The existing `agents.count` and `agents.assignments` machinery is unchanged; we add a new step that *partitions* the resolved spec list across islands:

```
total_agents = resolve_agent_specs(config)             # existing
partitioned  = partition_into_islands(specs, count=N)  # NEW: round-robin
```

`agents.assignments` (mix-and-match) is partitioned the same way — assignments distribute across islands as evenly as possible. `islands.agents_per_island` is computed, not specified, equal to `len(partitioned[island_id])`.

Per-agent setup (`_setup_and_start_agent`) gets one new parameter, `island_id`, threaded into:

- `.coral_island` breadcrumb (worktree path is `agents/<agent_id>/` — stable across migration).
- `setup_shared_state(...)` for the right island root.
- `setup_claude_settings` / `setup_codex_settings` etc. for permission rules that reference `coral_dir / "islands" / island_id / ...` instead of `coral_dir / "public" / ...`.
- CORAL.md generation (so prompts say "your shared state is at `.claude/...`" — no change visible to the agent, since the symlinks land in the same place).

### 4.7 Grader daemon scope

The grader daemon's `_find_pending` switches from globbing one attempts dir to globbing all islands' attempts dirs:

```python
def _find_pending(coral_dir: Path) -> list[Attempt]:
    if (coral_dir / "islands").exists():
        attempt_dirs = list((coral_dir / "islands").glob("*/attempts"))
    else:
        attempt_dirs = [coral_dir / "public" / "attempts"]
    pending = []
    for d in attempt_dirs:
        for p in d.glob("*.json"):
            attempt = read_attempt_file(p)
            if attempt and attempt.status == "pending" and attempt.score is None:
                pending.append(attempt)
    pending.sort(key=lambda a: a.timestamp)
    return pending
```

`_grade_one` writes the finalized attempt back via `write_attempt(island_root(...), ...)`. The grader pulls `island_id` from the attempt's `metadata.island_id` (set by `coral eval` at submit time — see §4.8) so it knows which dir to write back to. Worker pool size (`grader.parallel.max_workers`) is shared across islands. Per-island worker pools are not implemented in v1 — out-of-scope.

### 4.8 `coral eval` and submit-time metadata

`coral eval` (`coral/hooks/post_commit.py:submit_eval`) gains:

- Reads `.coral_island` from the worktree to determine which island.
- Stamps the new attempt's `metadata.island_id` field at submit time.
- Writes the pending attempt JSON to `island_root(coral_dir, island_id) / "attempts" / "<hash>.json"`.

The `island_id` field on `Attempt.metadata` becomes a **stable provenance marker** — even after migration moves the attempt JSON to another island's dir, `metadata.island_id` still records where it was *originally produced*. The new location is implicit in the file's path.

### 4.9 Per-island vs global eval count

- **Per-island** counter at `islands/<id>/eval_count` drives **per-agent heartbeat actions** on that island (so heartbeat triggers stay scoped to the island the agent lives on).
- **Global** counter at `.coral/eval_count` is incremented on every grade across any island. Migration cadence and global heartbeats (e.g. the `consolidate` action with `is_global=true`) read this counter.

The grader daemon's `increment_eval_count` becomes:

```python
with _eval_count_lock:
    increment_eval_count(coral_dir, island_id)   # per-island
    increment_global_eval_count(coral_dir)       # global
```

`hub.attempts.read_eval_count` gets an `island_id=None` parameter — `None` reads the global counter, otherwise the per-island one.

## 5. Configuration

```yaml
islands:
  count: 1                       # default = current single-island behavior
  migration:
    enabled: true                # ignored when islands.count == 1
    every: 50                    # global evals between migration cycles
    rank_window: 20              # "best agent" judged by max-over-last-N evals
    min_evals: 3                 # candidate must have ≥ N attempts to be eligible
    dest_weighting: score        # score | uniform | round_robin
    max_per_cycle: 1             # cap migrations per cycle (across all source islands)
    notify_island: true          # fire heartbeat ping to other agents on destination
```

Knockout config slot is **reserved** but absent in v1:

```yaml
# islands.knockout: {}            # FUTURE WORK — see §11
```

When `islands.count == 1`, the entire `islands.*` block is ignored and behavior is identical to today's CORAL.

Validation in `IslandsConfig.__post_init__`:

- `count >= 1` (default 1).
- `migration.every >= 1`.
- `migration.rank_window >= 1` and `<= migration.every`.
- `migration.min_evals >= 1`.
- `migration.dest_weighting` is one of `{"score", "uniform", "round_robin"}`.
- `migration.max_per_cycle >= 1`.

## 6. Migration mechanism

### 6.1 What moves

A migration **moves one live agent identity** from a source island to a destination island. The moving unit comprises:

| Artifact | Source path | Destination path | Collision behavior |
|---|---|---|---|
| **Role file** | `islands/<src>/roles/<aid>.md` | `islands/<dst>/roles/<aid>.md` | Cannot collide in normal operation because `<aid>` is globally unique. |
| **Heartbeat config** | `islands/<src>/heartbeat/<aid>.json` | `islands/<dst>/heartbeat/<aid>.json` | Existing destination file is replaced. |
| **Attempts authored by `<aid>`** | `islands/<src>/attempts/<hash>.json` and `*.jsonl` records filtered by `agent_id == aid` | `islands/<dst>/attempts/<hash>.*` | Existing destination file is replaced. |
| **Eval logs for moved attempts** | `islands/<src>/eval_logs/<hash>/` | `islands/<dst>/eval_logs/<hash>/` | Existing destination directory is replaced. |

What does **not** move:

- Notes and skills. They stay on the source island as island-local shared knowledge.
- The source island's other agents, attempts, logs, notes, skills, roles, and heartbeat files.
- The agent id prefix. `0-agent-1` keeps the `0-` birth-lineage prefix even after moving to island 1.

The agent process is interrupted, its worktree shared-state symlinks and `.coral_island` breadcrumb are repointed at the destination island, runtime permission settings are refreshed, and the manager restarts the same agent on the destination. v1 does not spawn a replacement agent on the source island.

### 6.2 Author attribution

Attempts already carry `agent_id`, which is enough for v1 migration to move the correct attempt records and matching eval logs. Notes and skills may still carry creator metadata for auditing and future features, but migration does not consume that metadata in v1.

### 6.3 Selection

Every `islands.migration.every` global evals (read from `.coral/eval_count`), the manager runs **one migration cycle**:

1. For each source island, consider current residents from the live roster, not from historical attempt locations.
2. Pick that island's best eligible resident using the best score over its last `rank_window` real attempts, requiring at least `min_evals` real attempts.
3. Assign each candidate a non-source destination via `dest_weighting`:
    - `score`: weight destinations by their current best score, direction-aware.
    - `uniform`: equal probability across non-source islands.
    - `round_robin`: deterministic shift by cycle index.
4. Select a final subset of at most `max_per_cycle` migrations that does not worsen per-island live-agent count balance. On an already-balanced two-island run, `max_per_cycle=2` permits a swap; `max_per_cycle=1` skips one-way moves that would create imbalance.

Edge cases:

- **Fewer than 2 islands** (e.g. `islands.count == 1` reached via override): migration is skipped silently.
- **No eligible candidate** (all source-island agents have fewer than `min_evals` attempts): that source island contributes no candidate for this cycle.
- **Pending attempt in flight**: see §6.6.

### 6.4 Cadence and trigger

Migration cycles are triggered from inside `AgentManager.monitor_loop`, on the same tick that already checks for new attempts and dead agents. Each tick:

`MigrationRunner` tracks the last completed eval boundary in memory. On resume, it starts from the current global counter and fires only after the configured interval is crossed.

### 6.5 Process lifecycle

A migration cycle is conceptually:

```
1. Quiesce migrating agent on source.
2. Move per-agent artifacts from source island to destination island.
3. Repoint the same worktree at the destination island.
4. Refresh runtime permissions and restart the same agent_id.
5. (Optional) Write an arrival note on the destination island.
```

Concretely, in `AgentManager`:

```python
def _apply_migration(candidate: MigrationCandidate) -> None:
    if agent_is_paused_or_has_pending_attempt(candidate.agent_id):
        defer_for_next_cycle(candidate)
        return
    interrupt_live_handle(candidate.agent_id)
    _move_agent_files(coral_dir, candidate.agent_id, src=candidate.src_island, dst=candidate.dst_island)
    repoint_shared_state(worktree, coral_dir, shared_dir_name, new_island_id=candidate.dst_island)
    _refresh_runtime_settings(..., island_id=candidate.dst_island)
    _swap_spec_island(candidate.agent_id, new_island_id=candidate.dst_island)
    _setup_and_start_agent(candidate.agent_id, island_id=candidate.dst_island, prompt=arrival_prompt)
```

The migrant arrival prompt (terse, hand-written):

> "You moved from island {src} to island {dst}. Your role, heartbeat cadence, attempts, and eval logs moved with you. Notes and skills remain island-local, so run `coral log` and `coral notes` to understand your new island before continuing."

### 6.6 Pending attempts

If the migrating agent has a pending attempt in the grader queue when migration triggers, the manager defers that candidate. Deferred candidates are retried at the next migration cycle and count against the same final `max_per_cycle` and roster-balance selection as fresh candidates.

### 6.7 Collision handling

- **Role/heartbeat/attempt/eval-log collision**: destination state is replaced. This keeps retries idempotent and makes the most recent migration attempt authoritative.
- **Notes/skills collision**: not applicable in v1 because notes and skills do not migrate.

### 6.8 Atomicity

Migration is **not transactional**. File moves are idempotent and replace existing destinations, but v1 does not persist a migration-in-progress marker or replay log. A crash in the middle of `_apply_migration` may require manual cleanup.

## 7. Agent-side experience

### 7.1 What changes for agents

**Almost nothing.** From inside the agent's worktree:

- `coral log` shows the leaderboard for *this island* (because the symlinked `attempts/` is the island's, not a global pool).
- `coral show <hash>` works for any commit in the shared object DB — so even if a migrant brings in attempts from another island, `coral show` works.
- `coral notes`, `coral skills` — read island-local state.
- `coral status` — manager-level command; in multi-island mode renders per-island sections (see §8.1). Available from inside or outside a worktree.
- The arrival of a migrant manifests as the agent appearing in that island's `coral log`, plus an optional arrival note written by the manager (§6.5).

### 7.2 Provenance hint in CORAL.md

The generated CORAL.md gets a one-paragraph note (only in multi-island runs):

> "You are working on island `<island_id>` in a multi-island run. Other islands exist with their own attempts, notes, and skills, but you cannot see their state directly. Periodically, a strong agent may migrate between islands; its role, heartbeat cadence, attempts, and eval logs move with it, while notes and skills remain island-local. You may notice teammates appearing or vanishing — this is normal."

That's the entire surface area. No new commands, no new file paths to memorize.

## 8. CLI surface

### 8.1 New / modified commands

- `coral log`
   - From inside an agent worktree: read the current island's leaderboard via the `.coral_island` breadcrumb.
   - From outside a worktree: aggregate across all islands.
- `coral status`
   - Multi-island runs render per-island sections. Each section shows that island's agents, their attempts, and their best score. A "Global best" header shows the across-island maximum.
- `coral runs [--all] [--task NAME]`
   - Unchanged. The run dir contains the islands; `coral runs` lists run dirs.
- `coral show <hash>`
   - From inside a worktree, resolves within the current island where applicable. From outside, scans all islands' attempts dirs.
- `coral notes`
- `coral skills`
   - Same scoped-vs-aggregate behavior as `coral log`.
- `coral heartbeat [set|remove|reset]`
   - Resolves `island_id` from the worktree breadcrumb, same as `coral eval`.

### 8.2 Web UI

- Dashboard API endpoints aggregate attempts, logs, agent status, skills, notes, and eval count across island roots.
- Per-island tabs and migration history are follow-up UI work; v1 does not persist a `migration_log.jsonl`.

### 8.3 `coral validate`

`coral validate <task>` already does a dry-run grade against `seed/`. No changes for v1 — validation is single-island by definition (it doesn't spawn agents).

## 9. Backward compatibility

- **Single-island runs** (`islands.count == 1` or `islands` block omitted): behavior is exactly as today. No `islands/` dir. No agent-id prefix. No new breadcrumbs. No grader daemon globbing changes (the daemon detects the missing `islands/` dir and falls back to the single attempts dir).
- **Resume of a single-island run**: works as today. `coral resume` reads the existing layout and never sees the multi-island code paths.
- **Resume of a multi-island run**: `reconstruct_paths` extends to discover islands by scanning `coral_dir / "islands"`. Pending attempts left in `islands/<id>/attempts/` are picked up by the daemon as today.
- **Existing tasks**: every task in `examples/` works unchanged in single-island mode. Adding `islands.count: 4` to a task's `task.yaml` is the only change needed to enable multi-island.

## 10. Implementation phases

The implementation breaks into independent phases that can each be a separate PR:

### Phase 1 — Foundations (no behavior change)
- Add `IslandsConfig` and `MigrationConfig` dataclasses to `coral/config.py`. Default `islands.count = 1`.
- Add `coral/hub/_island.py` with `island_root()` resolver.
- Thread `island_id` parameter through hub-module write/read functions, defaulting to `None` (single-island).
- Add `notes_by(agent_id)` in `hub.notes` and `skills_by(agent_id)` in `hub.skills`. Both filter on the existing `creator:` frontmatter field.
- Audit `coral/template/skills/*/SKILL.md` for `creator:` (should be absent on bundled skills).
- Update bundled `librarian` / `skill-creator` subagent templates and the heartbeat `consolidate` prompt to instruct stamping `creator: <agent_id>` (Phase 1's only prompt change).
- Tests: hub modules return identical results in single-island mode; `notes_by` / `skills_by` round-trip correctly; bundled skills are excluded from `skills_by`.

### Phase 2 — Island layout in workspace
- `coral/workspace/project.py`: when `islands.count > 1`, create `islands/<id>/{attempts,notes,skills,agents,roles,heartbeat,eval_logs,logs}` dirs and seed bundled skills/agent-templates per-island. Initialize per-island `eval_count` and the global `eval_count` at `.coral/eval_count`.
- `coral/workspace/worktree.py`: extend `setup_shared_state` to take `island_id`, point symlinks at the right island root. Write `.coral_island` breadcrumb.
- `setup_*_settings` (claude/codex/opencode/cursor): scope permission patterns to the agent's island root in multi-island mode.
- Globally-unique agent IDs in `agents.assignments` resolution.
- Tests: 2-island fixture run setup creates the right tree, agent worktrees have correct breadcrumbs, permissions allow writing to the right island.

### Phase 3 — Eval and grader-daemon island awareness
- `coral/hooks/post_commit.py:submit_eval`: read `.coral_island`, write attempt to `islands/<id>/attempts/`, stamp `metadata.island_id`.
- `coral/grader/daemon.py:_find_pending`: glob all islands' attempts dirs; `_grade_one` writes back to the right island.
- `increment_eval_count`: per-island + global counters.
- `agent_in_grader_queue`, `read_attempts`, `get_leaderboard`: take optional `island_id`.
- Tests: 2-island fixture with one pending attempt per island; grader finalizes both correctly; global counter reaches 2.

### Phase 4 — Manager partitioning
- `AgentManager.start_all`: partition specs across islands round-robin; spawn agents with their island_id. New helper `partition_into_islands(specs, count)`.
- `_setup_and_start_agent` gains an `island_id` parameter, threaded into worktree paths (`agents/<agent_id>/` — no island prefix in path), breadcrumb files, `setup_shared_state`, settings writers, and CORAL.md generation.
- `monitor_loop`: per-island heartbeat triggers (consume per-island eval_count); cross-agent notification within an island for heartbeat actions stays scoped to the agent's island.
- `_kill_old_agent_processes` and PID tracking remain global (agent IDs are globally unique, so no scoping needed).
- Tests: 2-island fixture, 2 agents per island, all spawn correctly with right worktrees and correct breadcrumbs.

### Phase 5 — Migration cycle
- `coral/agent/migration.py`: new module containing:
   - `select_candidates(...)`
   - `assign_destinations(...)`
   - `choose_roster_balanced_subset(...)`
   - `MigrationRunner`
- `AgentManager._maybe_run_migration_cycle`: orchestrates the lifecycle from §6.5.
- Migration arrival notes/prompts.
- Tests: unit tests for selection, destination weighting, roster-balanced final caps, file moves, and manager-level migration application.

### Phase 6 — CLI and UI surface
- Worktree-scoped CLI reads/writes via `.coral_island`; non-worktree CLI invocations aggregate across islands.
- `coral status` aggregates multi-island run state.
- Web API aggregates multi-island attempts/logs/status/events.
- Explicit `--island` flags and richer per-island Web views are deferred.

### Phase 7 — Knockout (TODO, separate spec)
Deferred. The directory layout and config schema are designed to absorb knockout without further refactor.

## 11. Testing

### Unit
- `island_root` resolver: single-island returns `public/`, multi-island returns the right subdir, raises on `island_id=None` in multi-island.
- `select_candidates` and `assign_destinations` for each `dest_weighting` mode and edge cases (1 island, 0 eligible candidates, all-tied scores).
- `choose_roster_balanced_subset`: max-per-cycle cap and live-agent count balance.
- `_move_agent_files`: moves role, heartbeat, attempts (`*.json` and `*.jsonl`), and matching eval logs; idempotent on retry.

### Integration
- 2-island fixture: spawn 2 agents per island, run a deterministic mock grader that ramps scores on one island faster than the other, force a migration cycle, verify:
   - The expected agent moves to the expected destination.
   - Source/destination live-agent counts follow the configured cap/balance policy.
   - Attempts and eval logs follow the migrated agent.
- Resume after migration: verify worktree breadcrumbs and manager roster restore the current island rather than birth island.
- Single-island run still passes the existing test suite unchanged (regression gate).

### End-to-end
- One real example task (`examples/circle_packing` is the smallest fast one) runs successfully with `islands.count: 2`, completes ≥ 1 migration cycle, and produces a leaderboard with attempts from both islands.

## 12. Open questions / future work (knockout TODO)

1. **Knockout-and-respawn**. v2 will add `islands.knockout` config (`every`, `fraction`, `rank_window`). Mechanism: every K global evals, rank islands, eradicate the bottom fraction (wipe `attempts/`, `notes/`, `roles/`, `heartbeat/`; keep `skills/`), seed the eradicated island with a digest from the winner, and restart all its agents fresh.
2. **Cross-island reading by agents**. Could be added later (`coral log --island N` from inside any worktree) without architectural changes — just expand the CLI's island-id resolution to accept an explicit override. Deferred because it adds a mental-model surface we don't need for v1.
3. **Per-island grader pools**. v1 shares `grader.parallel.max_workers` across islands. If different islands run vastly different graders (mix-and-match scenario), per-island pools may be useful. Not needed yet.
4. **Hot island count change**. v1 fixes `islands.count` at run start. Adding/removing islands during a run is out of scope; the resume path validates that the current islands count matches the saved config.
5. **Migration prompt tuning.** The arrival prompt/note is hand-written in v1. After a few real runs we should iterate on whether agents respond well to it.
6. **Skill/note migration.** v1 leaves notes and skills island-local. If cross-island knowledge transfer is too weak, a later version can add creator-filtered note/skill copy semantics.

## 13. Glossary

- **Island** — an isolated subtree under `.coral/islands/<id>/` with its own attempts, notes, skills, roles, heartbeat config, and eval counter. Agents on an island only ever read state from their own island.
- **Migration** — moving one live agent identity (role + heartbeat + attempts + eval logs) from a source island to a destination island, then restarting that same agent on the destination.
- **Migrating agent** — the strongest-scoring agent on the source island in this cycle.
- **Destination island** — chosen by `dest_weighting`, biased toward weaker islands by default.
- **Replacement agent** — deferred v2 concept; v1 does not spawn a replacement on the source island.
- **Globally-unique agent ID** — `<birth_island_id>-<aid_within_island>` in multi-island mode (e.g. `0-agent-2`). The prefix is the birth-island lineage marker and is stable across migration.
- **Island root** — `coral_dir / "public"` in single-island mode; `coral_dir / "islands" / island_id` in multi-island mode. The base path for hub-module reads/writes.
