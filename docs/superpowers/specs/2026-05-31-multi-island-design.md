# Multi-Island CORAL with Agent Migration

**Status:** Design draft — knockout deferred to follow-up.
**Author:** brainstormed with Claude.
**Scope:** v1 = islands + migration. v2 (TODO) = knockout-and-respawn.

## 1. Goal

Run multiple isolated CORAL "islands" inside a single run. Each island is a self-contained shared-knowledge space (its own attempts, notes, skills, roles); agents on an island only ever read their own island's state, with the same primitives they use today. Periodically, the **best-performing agent on one island migrates** to another island, carrying its full contribution (role, attempts, notes, skills) so that good work cross-pollinates without erasing the diversity that island isolation creates.

The framework's job is selection and bookkeeping. The agents' job is the same as today: read shared state, do work, write shared state. Migration is a manager-side mechanism the agents do not need to understand explicitly.

## 2. Non-goals

- **Knockout-and-respawn** is deferred. v1 ships migration only. The directory layout and config schema are designed so knockout slots in later without a migration.
- **Cross-island reading** by agents during normal work (e.g. `coral log --island 2` from inside island 0). The infrastructure could support it, but it adds another mental model surface and the user prefers selection-only for v1.
- **Skill conflict resolution** beyond filename renaming. If two islands' skills with the same name end up co-resident on the destination, we rename the migrant; we do not try to merge.
- **Cross-run migration** (between separate `coral start` invocations). All islands live inside one run.
- **Heterogeneous islands** (different runtimes / models per island). Existing `agents.assignments` mix-and-match remains unchanged; islands are partitions of the resolved agent pool.

## 3. Background

The arxiv reference (2506.13131 — AlphaEvolve) cites "island-based population models" exactly once, pointing at FunSearch [97] for the actual mechanism. In FunSearch, the **individual is a single program**; "migration" is really *island reset* (every M iterations, the worst-half islands are wiped and reseeded from a top island's program clusters). Pure migration — copying individuals between islands without erasing — is the older island-model GA pattern.

CORAL is meaningfully different from FunSearch:

- The "individual" is not just a program. It is an **agent + their accumulated context** (notes, skills, role, attempts).
- Knowledge accumulates in the shared `.coral/public/` directory over the lifetime of a run. Wiping that knowledge on a few bad rolls is wasteful in a way it is not in FunSearch.
- Agents read shared state through `coral log`, `coral show`, `coral notes`, `coral skills`, and reading files under `.claude/`. Any new mechanism that does not flow through these primitives is invisible to them.

The design below treats the **agent's full contribution** as the migrating unit and routes everything through CORAL's existing reading surface.

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
│   │       ├── _agent_seq            # next agent slot # (NEW; see §4.4)
│   │       └── .git                  # per-island checkpoint repo (NEW; see §4.3)
│   ├── eval_count                    # GLOBAL counter (kept for migration cadence)
│   ├── migration_cursor              # cadence + RR state (NEW; see §6.4)
│   ├── migration_log.jsonl           # append-only history (NEW; see §8.2)
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

The replacement agent that island 0 spawns to fill the vacated slot gets a fresh ID with the next available sequence number for that island (e.g. `0-agent-3`, then `0-agent-4`, ...). Sequence numbers are tracked in a per-island file `islands/<id>/_agent_seq` (a small text counter, written atomically).

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

A migration moves **one agent's full contribution** from a source island to a destination island. The migrating unit comprises:

| Artifact | Source path | Destination path | Collision behavior |
|---|---|---|---|
| **Role file** | `islands/<src>/roles/<aid>.md` | `islands/<dst>/roles/<aid>.md` | Cannot collide — `<aid>` is globally unique. |
| **Attempts authored by `<aid>`** | `islands/<src>/attempts/<hash>.json` (filtered by `agent_id == aid`) | `islands/<dst>/attempts/<hash>.json` | Cannot collide — commit hashes are globally unique in the shared object DB. |
| **Notes authored by `<aid>`** | `islands/<src>/notes/**/*.md` filtered by frontmatter `creator: <aid>` | `islands/<dst>/notes/<original-relative-path>.md` | On filename collision, prefix with `<aid>-`. |
| **Skills authored by `<aid>`** | `islands/<src>/skills/<name>/` filtered by SKILL.md frontmatter `creator: <aid>` | `islands/<dst>/skills/<name>/` | On directory collision, rename to `<name>-from-island-<src>/`. |

What does **not** move:

- The agent's session ID (reset on arrival; new session starts fresh on the destination worktree).
- The agent's heartbeat config (re-seeded from `default_local_actions(config)` on arrival, same as a fresh agent).
- `eval_logs/` (stays on source — those are per-attempt grader artifacts and the attempts that reference them are already being copied; the eval_log path becomes a cross-island reference but `coral show` does not currently read eval_logs, so no breakage).
- The agent's runtime process (killed on source, fresh process spawned on destination).

**Source island retains everything.** Migration is a *copy*, not a move, for all four artifact types. This preserves historical reference on the source island so other source-side agents can still see "agent-X's old work." The agent process is the only thing that strictly moves.

### 6.2 Author attribution

The migration mechanism needs to filter notes and skills by author. Today:

- **Attempts** already carry `agent_id` — no change needed.
- **Notes** are markdown with YAML frontmatter. `coral/hub/notes.py` already parses a `creator:` field from each note's frontmatter — we reuse it. Notes with `creator: <aid>` are eligible to migrate; notes without `creator:` (or with mismatched values) stay on the source island.
- **Skills** have a SKILL.md with frontmatter. `coral/hub/skills.py` already reads a `creator:` field — we reuse it. Skills with `creator: <aid>` migrate; skills without `creator:` are treated as bundled-framework skills (deep-research, librarian, etc., which are seeded per-island already) and **not migrated**.

The bundled `coral/template/skills/*/SKILL.md` files will be audited as part of Phase 1 to confirm none have a `creator:` field — those that do will be cleaned up so they don't accidentally migrate.

**Reliability of `creator:` stamping is a soft dependency.** If an agent writes a note via `Write` directly without a `creator:` field, it will not migrate. Mitigations:

- Bundled `librarian` / `skill-creator` subagent templates and the heartbeat `consolidate` prompt are updated (Phase 1) to instruct stamping `creator: <agent_id>` in frontmatter — agents already know their `agent_id` from the `.coral_agent_id` breadcrumb.
- A small helper command `coral note new <slug>` (Phase 1) is offered: it takes a body on stdin, writes the file under the current island's `notes/` with `creator:` and `created:` pre-stamped. Optional — agents that don't use it just don't get migration for their notes.

We deliberately do not auto-stamp notes via a post-write hook: that adds invisible behavior to a file-write the agent thinks it controls, and creates trouble if the agent expected the file content to match exactly what they wrote.

### 6.2.1 Filter helpers

Add to `coral/hub/notes.py`:

```python
def notes_by(coral_dir: Path, island_id: str | None, agent_id: str) -> list[Path]:
    """Return absolute paths of notes whose frontmatter `creator` matches agent_id."""
```

Add to `coral/hub/skills.py`:

```python
def skills_by(coral_dir: Path, island_id: str | None, agent_id: str) -> list[Path]:
    """Return absolute paths of skill directories whose SKILL.md frontmatter `creator` matches agent_id."""
```

Both honor the multi-island layout via `island_root()`.

### 6.3 Selection

Every `islands.migration.every` global evals (read from `.coral/eval_count`), the manager runs **one migration cycle**:

1. **Score each island.** For each island, compute `island_score[i] = max(score for attempt in islands/<i>/attempts/* with score is not None and submitted within last rank_window evals on that island)`. Treat unscored islands as `-inf` (maximize) or `+inf` (minimize).
2. **Pick a source island.** The source is the island with the *highest* island score (for `direction = maximize`).
3. **Pick the migrating agent.** On the source island, find the agent with the highest `max(score)` over their last `rank_window` attempts. Filter to agents with at least `min_evals` finalized attempts. Ties broken by most-recent-best-score timestamp.
4. **Pick the destination island.** Excluding the source, rank the remaining islands by `island_score` (best first), then weight by `dest_weighting`:
    - `score`: rank-based, rescue-biased. The lowest-ranked (worst) destination gets the highest weight: `weight[i] = rank[i]` where `rank[i] = 1` for the best remaining and `N-1` for the worst. Probability `∝ weight[i]`. Robust to score magnitude, sign, and direction.
    - `uniform`: equal probability.
    - `round_robin`: rotate through destinations in island-id order, persisted via `.coral/migration_rr_cursor`.
5. **Cap.** At most `max_per_cycle` migrations per cycle (default 1). If multiple cycles fall on the same eval boundary (shouldn't happen but defensive), still cap to `max_per_cycle`.

Edge cases:

- **Fewer than 2 islands** (e.g. `islands.count == 1` reached via override): migration is skipped silently.
- **No eligible candidate** (all source-island agents have fewer than `min_evals` attempts): migration is skipped this cycle, retried next cycle.
- **Pending attempt in flight**: see §6.6.

### 6.4 Cadence and trigger

Migration cycles are triggered from inside `AgentManager.monitor_loop`, on the same tick that already checks for new attempts and dead agents. Each tick:

```python
global_evals = read_global_eval_count(coral_dir)
if global_evals >= self._next_migration_at:
    self._run_migration_cycle()
    self._next_migration_at = global_evals + config.islands.migration.every
```

The `_next_migration_at` cursor is initialized to `config.islands.migration.every` at startup (so the first migration fires after `every` evals, not at startup) and persisted to `.coral/migration_cursor` so resume picks up where it left off.

### 6.5 Process lifecycle

A migration cycle is conceptually:

```
1. Quiesce migrating agent on source.
2. Copy artifacts from source island to destination island.
3. Stop source agent's process.
4. Start fresh process on destination worktree (same agent_id).
5. Spawn replacement agent on source.
6. (Optional) Notify destination island.
```

Concretely, in `AgentManager`:

```python
def _run_migration_cycle(self) -> None:
    cycle = self._select_migration_candidate()
    if cycle is None:
        return
    src_island, dst_island, aid = cycle

    # 1. Wait for any pending attempt from this agent to finalize.
    self._wait_for_pending(aid, timeout=self.config.agents.grader_pending_max_age)

    # 2. Copy artifacts (idempotent, atomic per-file via tmp+rename).
    copy_agent_contribution(
        coral_dir=self.paths.coral_dir,
        agent_id=aid,
        src_island=src_island,
        dst_island=dst_island,
    )

    # 3. Stop source process. Use SIGINT first to save session, fall back to SIGTERM.
    src_handle = self._find_handle(aid)
    src_handle.stop()

    # 4. Rebuild the worktree in place: `git worktree remove agents/<aid>` then
    #    `git worktree add agents/<aid> coral/<aid>`. Path is stable; only the
    #    symlinks (via setup_shared_state) and .coral_island breadcrumb change
    #    to target the destination island. Per-agent counters (eval count,
    #    score history, plateau anchors) are reset on arrival — fresh start.
    new_handle = self._setup_and_start_agent(
        agent_id=aid,
        island_id=dst_island,
        prompt=self._migration_arrival_prompt(src_island, dst_island),
        prompt_source="migration:arrival",
    )
    self._replace_handle(aid, new_handle)

    # 5. Spawn replacement on source.
    replacement_aid = self._next_agent_id_for_island(src_island)  # e.g. "0-agent-3"
    self._setup_and_start_agent(
        agent_id=replacement_aid,
        island_id=src_island,
        prompt=self._replacement_intro_prompt(src_island, aid),
        prompt_source="migration:replacement",
    )

    # 6. Notify destination island agents (other than the migrant itself).
    if self.config.islands.migration.notify_island:
        for other_handle in self._island_handles(dst_island):
            if other_handle.agent_id == aid:
                continue
            self._interrupt_and_resume(
                self._handle_index(other_handle.agent_id),
                self._migration_neighbor_prompt(aid, src_island),
                prompt_source="migration:neighbor",
            )
```

The migrant arrival prompt (terse, hand-written):

> "You moved from island {src} to island {dst}. Your role, attempts, notes, and skills came with you. The other agents here are working on the same task but with different history. Run `coral log` and `coral notes` to see their work; carry on from where you left off."

The neighbor prompt:

> "Agent {aid} just joined this island from island {src} — they brought their attempts, notes, and skills with them. Run `coral log` and `coral notes` to see their work, then decide whether their approach changes what you should be doing."

The replacement prompt (for the rookie spawned on source):

> "You are a fresh agent on island {src}. Your predecessor was the strongest contributor here and migrated to another island. Read the existing notes, attempts, and skills on this island to catch up, then start contributing."

### 6.6 Pending attempts

If the migrating agent has a pending attempt in the grader queue when migration triggers:

- **Wait for it to land** (up to `agents.grader_pending_max_age` seconds — we already have this knob).
- The finalized attempt is then included in the artifacts copied to the destination.
- If it times out before finalizing, log a warning and skip the wait — the pending attempt stays on the source island (its `agent_id` won't match anyone live there, but that's harmless; the leaderboard record is still valid).

### 6.7 Collision handling

- **Notes filename collision** (`notes/<x>.md` exists on destination): rename the migrant's copy to `notes/<aid>-<x>.md` to preserve both. Do not overwrite — even if both notes are by the same agent (impossible in v1 since `<aid>` is unique, but defensive).
- **Skills directory collision** (`skills/<name>/` exists on destination): rename the migrant's directory to `skills/<name>-from-island-<src>/`. If SKILL.md has a `name:` field in frontmatter, update it to match the new directory name (otherwise leave SKILL.md unchanged; `list_skills` falls back to the directory name).
- **Attempt JSON collision** (`attempts/<hash>.json` exists on destination): impossible in practice — commit hashes are globally unique. If it ever happened (e.g. corruption), prefer the existing destination copy and log a warning.
- **Role file collision**: impossible — `<aid>` is globally unique.

### 6.8 Atomicity

Migration is **not transactional**. If we crash mid-copy, partial state on the destination island is possible. Mitigations:

- **Per-file atomicity**: every file write goes through tmp + rename (already the pattern in `hub.attempts.write_attempt`). Notes and skills get the same treatment.
- **Idempotent retry**: a migration cycle that crashed mid-way leaves a `migration_in_progress` marker file at `.coral/migration_in_progress`. On manager startup (including resume), if this marker exists, the manager retries the migration step it was on (file copies are idempotent). The marker is removed only after the destination process is successfully started.
- **Source agent already stopped**: if the source process was stopped before the crash but the destination process never started, the next manager tick observes a missing handle and treats it as a dead agent — the existing `_restart_agent` path will resume the agent on its current worktree. To avoid resurrecting the source, the marker file also records the post-migration island; the dead-agent restart path consults it.

For v1 we accept that a sufficiently bad crash mid-migration may require manual cleanup. Migration is rare (every `every >= 50` evals) so the exposure window is small.

## 7. Agent-side experience

### 7.1 What changes for agents

**Almost nothing.** From inside the agent's worktree:

- `coral log` shows the leaderboard for *this island* (because the symlinked `attempts/` is the island's, not a global pool).
- `coral show <hash>` works for any commit in the shared object DB — so even if a migrant brings in attempts from another island, `coral show` works.
- `coral notes`, `coral skills` — read island-local state.
- `coral status` — manager-level command; in multi-island mode renders per-island sections (see §8.1). Available from inside or outside a worktree.
- The arrival of a migrant manifests as: new attempts in `coral log`, new notes in `notes/`, new skills in `skills/`, plus a heartbeat-style prompt injected by the manager (§6.5).

### 7.2 Provenance hint in CORAL.md

The generated CORAL.md gets a one-paragraph note (only in multi-island runs):

> "You are working on island `<island_id>` in a multi-island run. Other islands exist with their own attempts, notes, and skills, but you cannot see their state directly. Periodically, the strongest-performing agent on one island migrates to another, bringing their attempts, notes, and skills with them. You may notice teammates appearing or vanishing — this is normal."

That's the entire surface area. No new commands, no new file paths to memorize.

## 8. CLI surface

### 8.1 New / modified commands

- `coral log [--island N] [--all-islands]`
   - With `--island N`: read leaderboard from `islands/N/attempts/`. Available from anywhere (does not require an agent worktree).
   - With `--all-islands`: stack per-island leaderboards. Default for `coral log` invoked from a non-worktree cwd.
   - Without flags from inside a worktree: read the current island's leaderboard (existing behavior, just with island-aware path resolution).
- `coral status`
   - Multi-island runs render per-island sections. Each section shows that island's agents, their attempts, and their best score. A "Global best" header shows the across-island maximum.
- `coral runs [--all] [--task NAME]`
   - Unchanged. The run dir contains the islands; `coral runs` lists run dirs.
- `coral show <hash> [--island N]`
   - `--island N` overrides the JSON-lookup island. Without it, scans all islands' attempts dirs (since hashes are globally unique).
- `coral notes [--island N]`
- `coral skills [--island N]`
- `coral heartbeat [set|remove|reset]`
   - Resolves `island_id` from the worktree breadcrumb, same as `coral eval`.

### 8.2 Web UI

- Per-island leaderboard tabs (or columns).
- Per-island agent status.
- Global header: "Best score across all islands."
- A "Migration history" panel (small, collapsed by default) showing the cycle history: `[eval #N] 0-agent-2 migrated from island 0 to island 1`. Sourced from `.coral/migration_log.jsonl` (new file, append-only).

### 8.3 `coral validate`

`coral validate <task>` already does a dry-run grade against `seed/`. No changes for v1 — validation is single-island by definition (it doesn't spawn agents).

## 9. Backward compatibility

- **Single-island runs** (`islands.count == 1` or `islands` block omitted): behavior is exactly as today. No `islands/` dir. No agent-id prefix. No new breadcrumbs. No grader daemon globbing changes (the daemon detects the missing `islands/` dir and falls back to the single attempts dir).
- **Resume of a single-island run**: works as today. `coral resume` reads the existing layout and never sees the multi-island code paths.
- **Resume of a multi-island run**: `reconstruct_paths` extends to discover islands by scanning `coral_dir / "islands"`. The migration cursor is read from `.coral/migration_cursor`. Pending attempts left in `islands/<id>/attempts/` are picked up by the daemon as today.
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
- Optional helper: `coral note new <slug>` CLI command that pre-stamps `creator:` and `created:`.
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
   - `select_candidate(coral_dir, config) -> tuple[src_id, dst_id, aid] | None`
   - `copy_agent_contribution(coral_dir, agent_id, src_island, dst_island)`
   - `MigrationCursor` (persists `_next_migration_at` and round-robin state)
- `AgentManager._wait_for_pending(aid, timeout)`: new helper that polls until the agent has no pending attempts (or timeout). Reuses `count_agent_pending`.
- `AgentManager._run_migration_cycle`: orchestrate the lifecycle from §6.5.
- Migration arrival/neighbor/replacement prompts (constants in `coral/agent/migration.py`).
- `.coral/migration_cursor`, `.coral/migration_log.jsonl`, and `migration_in_progress` marker for crash recovery.
- Tests: unit tests for `select_candidate` (each weighting mode), `copy_agent_contribution` (collision handling on notes/skills, idempotency), and a manager-level integration test that triggers one migration cycle in a 2-island fixture.

### Phase 6 — CLI and UI surface
- `--island` flag on `coral log`, `coral show`, `coral notes`, `coral skills`.
- `coral status` per-island rendering.
- Web UI per-island view + migration history panel.
- Tests: CLI surface tests with `--island` flag; rendering smoke tests.

### Phase 7 — Knockout (TODO, separate spec)
Deferred. The directory layout, config schema (`islands.knockout: {}` slot), and `migration_log.jsonl` plumbing are designed to absorb knockout without further refactor.

## 11. Testing

### Unit
- `island_root` resolver: single-island returns `public/`, multi-island returns the right subdir, raises on `island_id=None` in multi-island.
- `notes_by(agent_id)` / `skills_by(agent_id)`: filter by frontmatter, exclude bundled skills.
- `select_candidate` for each `dest_weighting` mode and edge cases (1 island, 0 eligible candidates, all-tied scores).
- `copy_agent_contribution`: collision rename for notes and skills, idempotency (run twice → no duplication), atomicity (mid-copy crash leaves no half-files visible to readers).
- `MigrationCursor`: persistence across restarts, monotonic increment.

### Integration
- 2-island fixture: spawn 2 agents per island, run a deterministic mock grader that ramps scores on one island faster than the other, force a migration cycle, verify:
   - The expected agent moves to the expected destination.
   - Source island has a fresh replacement agent.
   - Destination island's neighbor receives a heartbeat-style prompt (assert via log inspection).
   - Migration is recorded in `migration_log.jsonl`.
- Resume-mid-migration: simulate a crash with `migration_in_progress` marker present; verify `coral resume` retries cleanly without duplicating artifacts.
- Single-island run still passes the existing test suite unchanged (regression gate).

### End-to-end
- One real example task (`examples/circle_packing` is the smallest fast one) runs successfully with `islands.count: 2`, completes ≥ 1 migration cycle, and produces a leaderboard with attempts from both islands.

## 12. Open questions / future work (knockout TODO)

1. **Knockout-and-respawn**. v2 will add `islands.knockout` config (`every`, `fraction`, `rank_window`). Mechanism: every K global evals, rank islands, eradicate the bottom fraction (wipe `attempts/`, `notes/`, `roles/`, `heartbeat/`; keep `skills/`), seed the eradicated island with a digest from the winner, restart all its agents fresh. Reuses the migration artifact-copy primitive. Same `migration_log.jsonl` extended with knockout entries.
2. **Cross-island reading by agents**. Could be added later (`coral log --island N` from inside any worktree) without architectural changes — just expand the CLI's island-id resolution to accept an explicit override. Deferred because it adds a mental-model surface we don't need for v1.
3. **Per-island grader pools**. v1 shares `grader.parallel.max_workers` across islands. If different islands run vastly different graders (mix-and-match scenario), per-island pools may be useful. Not needed yet.
4. **Hot island count change**. v1 fixes `islands.count` at run start. Adding/removing islands during a run is out of scope; the resume path validates that the current islands count matches the saved config.
5. **Migration prompt tuning**. The arrival / neighbor / replacement prompts are hand-written in v1. After a few real runs we should iterate on whether agents respond well to them and whether the neighbor interrupt is too disruptive (and might be better as a passive note instead).
6. **Skill creator-attribution discipline.** Migration filters skills by SKILL.md frontmatter `creator: <agent_id>`. v1 ships with bundled subagent prompts and a `coral note new` helper that stamp this for the agent (see §6.2), but agents that author skills via raw `Write` calls without stamping `creator:` will have those skills silently excluded from migration. After a few real runs we should check whether this is reliable enough or whether we need stronger enforcement (e.g. a settings hook that rewrites SKILL.md on close).

## 13. Glossary

- **Island** — an isolated subtree under `.coral/islands/<id>/` with its own attempts, notes, skills, roles, heartbeat config, and eval counter. Agents on an island only ever read state from their own island.
- **Migration** — copying one agent's full contribution (role + attempts + notes + skills) from a source island to a destination island, then physically moving the agent's process to the destination and spawning a replacement on the source.
- **Migrating agent** — the strongest-scoring agent on the source island in this cycle.
- **Destination island** — chosen by `dest_weighting`, biased toward weaker islands by default.
- **Replacement agent** — a fresh, blank-roled rookie spawned on the source island to fill the slot vacated by the migrant.
- **Globally-unique agent ID** — `<birth_island_id>-<aid_within_island>` in multi-island mode (e.g. `0-agent-2`). The prefix is the birth-island lineage marker and is stable across migration.
- **Island root** — `coral_dir / "public"` in single-island mode; `coral_dir / "islands" / island_id` in multi-island mode. The base path for hub-module reads/writes.
