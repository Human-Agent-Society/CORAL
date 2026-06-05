---
name: create-notes
description: "Write a note to {shared_dir}/notes/ that future agents can actually act on. Use after every coral eval, when a heartbeat (reflect / consolidate / pivot) asks for a note, or when you discover a grader / build / runtime issue that future agents will hit. Covers 4 note variants (experiment / infra / focus / synthesis), required frontmatter with the team-level `creator:` filter, the self-audit checklist (backfilled predictions, abandoned paths, sourced magic numbers, cross-links), and the shell-escaping gotchas that silently strip markdown content. Trigger this skill whenever you are about to Write a file under notes/ — even if the prompt didn't say 'write a note'."
---

# Create Notes

A good note answers three questions a future agent will actually ask:

1. **What did you do, and what happened?** (concrete numbers, not adjectives)
2. **Why did it happen that way?** (the mechanism, not just the result)
3. **What should I do — or not do — given this?** (ordered next steps + things you tried that failed)

A bad note is a wall of headings with empty bodies, or a final-design pitch with no record of the alternatives you rejected. The bad pattern shows up enough that this skill exists to prevent it.

## When to Use

Each heartbeat that produces a note corresponds to one variant. The skill is one document, but you only need the variant your current trigger asks for.

| Triggered by | Variant | File location |
|---|---|---|
| `reflect` heartbeat after each eval | **Experiment note** (Variant A) | `notes/experiments/eval-<N>-<slug>.md` |
| `pivot` plateau detection | **Focus note** (Variant C) | `notes/focus-<topic>.md` |
| `consolidate` synthesis / connections / open-questions | **Synthesis + map + gaps** (Variant D) | `notes/_synthesis/<topic>.md`, `notes/_connections.md`, `notes/_open-questions.md` |
| First time a grader / build / runtime issue is hit | **Infra note** (Variant B) | `notes/infra/<slug>.md` (or `notes/<slug>.md`) |
| `deep-research` warm-start phase | **Research note** | Per `deep-research/SKILL.md` (not duplicated here) |

If you are about to `Write` any file under `notes/`, stop and use this skill first — even if the prompt did not say "write a note."

## Notes Directory Layout

The directory structure is owned by `organize-files`. Do not invent new top-level subdirectories; place new content in the right existing one:

```
notes/
├── index.md              ← table of contents; you update this for any new note
├── raw/                  ← immutable sources (do not write here directly)
├── research/             ← deep-research findings (link back to raw/)
├── experiments/          ← per-eval reflections, written by the reflect heartbeat
├── infra/                ← grader / build / runtime issues + workarounds (recommended)
├── focus-<topic>.md      ← per-agent focus declarations (owned by the pivot heartbeat)
├── _synthesis/           ← owned by consolidate; do not write here unless consolidating
├── _connections.md       ← owned by consolidate
├── _open-questions.md    ← owned by consolidate
└── _organization-log.md  ← append-only audit log; only organize-files writes here
```

**Always update `index.md`** with a one-line entry when you create a new note. The next agent's first move is to read it.

---

## Note Variants

### Variant A — Experiment note (reflect heartbeat, 7 sections)

This is the default for per-eval reflection. Use for any note describing what you tried in a single attempt or a small set of related attempts.

```markdown
---
creator: <your agent_id, from .coral_agent_id>
created: <ISO-8601 timestamp>
commit: <the coral eval commit hash this note describes, or "n/a">
---

# <Verbed noun phrase>: <one-line top-line result>

Examples of a good title:
- "V2 IVF real-mode: 1M SIFT1M, 1,251 QPS @ recall 0.9731"
- "Grader infra: benchmark binary mtime drift after every eval"

A bad title is "Experiment notes" or "V2 results" — they don't tell the next agent what the headline number is.

## Context
What task, what mode (tune / real), what input size, what config. One short paragraph.
Link the focus note if one exists: `Based on focus: [focus-1-agent-1-ivf-u8-simd.md](../focus-1-agent-1-ivf-u8-simd.md)`

## Result
Top-line numbers in a table. Include deltas vs the relevant baseline, not just absolutes.
| Metric | Baseline | This | Δ |
|---|---|---|---|
| ... | ... | ... | ... |

If there is a score, call it out on its own line: **score: 1,251.12**

## Mechanism
Why did it work (or not)? 3-6 bullet points naming the actual cause, not the symptom.
Good: "Memory ceiling is 7.5 MB / 50 GB/s = 6600 QPS; we are at 1251, so the gap is HTTP/JSON + 4096-centroid scoring."
Bad: "It was slow because of overhead."

## What did not work (or was considered and rejected)
2-3 entries minimum. Future agents will repeat your work otherwise.
Format: **Approach** — why it lost. One line each. Cite the eval/note that tested it if applicable.

Examples:
- **f64 storage + scalar loop** — 2x register footprint, 2x ops per dim; predicted 2x slower, observed 2.3x. Note: rejected before this run; revisit only if a fast f64 SIMD path appears.
- **nlist=2048** — centroid scoring halves but recall drops to 0.93 (below 0.95 gate). Tried in attempt `9ab3c4d`; do not retry without first raising per-probe quality.

## Surprises / open questions
- Things you predicted correctly that you are now uncertain about
- Things you did not predict at all
- Anything that contradicts a teammate's note (cite the contradiction explicitly)

## Next
2-5 actions in **descending expected payoff**. For each, name the lever, the expected multiplier, and the risk.

1. **u8 storage + SIMD u8 widening** — 4x memory compression, hot loop reads 4x fewer bytes. Expect 2-3x QPS. Risk: precision loss on recall — gate at 0.95+.
2. **Reduce nlist to 2048** — trivially doable. Expect ~10% QPS. Risk: see "What did not work" above.
3. **Rayon-parallelize the 64-probe scan** — expect 1.5-2x QPS. Risk: tokio + rayon interaction; smoke-test under load.

## References
- attempt `<hash>`: `coral show <hash>` — leaderboard entry + grader stderr
- attempt `<hash2>`: ... — the failed/rejected approach above
- focus note: [focus-...md](../focus-...md)
- prior note: [v1-real-mode.md](v1-real-mode.md) — baseline this builds on
- external: <paper / doc / benchmark URL or path>
```

Skip a section only if it is genuinely empty. "What did not work" is the one most often skipped — that is exactly the section you should not skip.

### Variant B — Infra note (grader / build / runtime issue)

Same shape as an experiment note but framed for diagnosis + workaround. Use the first time you hit an issue that future agents will also hit.

```markdown
---
creator: <agent_id>
created: <ISO-8601>
commit: n/a
---

# <Infra area>: <one-line symptom>

## Context
- Which task, which mode, which trigger condition

## Result
| Eval | Mode | Outcome |
|---|---|---|
| #11 | real | FAILED: <error text, copied verbatim> |
| #11 (retry) | real | OK after <workaround> |

## Mechanism
- Cite the grader / build / runtime code path
- Explain why the failure is structural, not a one-off

## What did not work
- 2-3 workaround attempts that failed (and why). Often: "tried X — got Y error — read source, X cannot work because Z."

## Surprises
- Things you thought would fix it but didn't

## Next
1. **Pre-eval step** to apply the workaround (with the exact command). Cost. Risk.
2. **Upstream fix** to push the issue to a permanent solution (which file / which repo / which person).

## References
- The failed attempt hash
- The succeeded attempt hash (post-workaround)
- The grader source file path
- related: `_open-questions.md` → "..."
```

### Variant C — Focus note (pivot heartbeat)

This is the contract you make with the team when you change direction. It is a public declaration so other agents can pick a different lane.

```markdown
---
creator: <agent_id>
created: <ISO-8601>
generation: 1  # bump when direction meaningfully shifts
---

# Focus: <short topic>

## Posture
What functional role you are playing for the team.
- engineer | researcher | performance engineer | tooling engineer | reviewer | tech writer
- (or your own variant — name it.)
Pick the posture **most missing** from the current team, not the most comfortable.

## Lane
The specific technique, area, or composite you are attempting.

## Budget
How many evals you intend to spend before judging.

## Abandon-if
Specific score, recall, or failure mode that would convince you to stop.
(Must be concrete and testable, not a vibe.)

## Why this has positive EV
- What evidence (in the team's notes) suggests this is worth trying
- Which other agents' work this builds on or complements
- Why the easy alternatives have been ruled out

## Update history
- <ISO-8601>: created
```

`generation` is bumped when the direction meaningfully shifts, not on every eval. A stable focus note across many evals is a healthy signal.

### Variant D — Synthesis / Connections / Open-questions (consolidate heartbeat)

Three different output shapes, all under the consolidate trigger. Pick the one that fits; at least one is required per consolidate pass.

**D.1 Synthesis note** (`notes/_synthesis/<topic>.md`) — distill 3+ related notes into a single claim:

```markdown
---
creator: <agent_id>
created: <ISO-8601>
---

# <Topic>: <one-line conclusion>

**Summary:** <The claim, stated in one sentence, with the conditions under which it holds.>

**Evidence:**
- attempt <hash1>: <result> — <one line>
- attempt <hash2>: <result> — <one line>
- attempt <hash3>: <result> — <one line>

**Why it works:** <Mechanism, 2-4 sentences.>

**Confidence:** <High / Medium / Low> for <condition>. Uncertain for <other condition>.

**Counter-evidence:** <Where this might be wrong, if any.>
```

A synthesis note is **not** a dump of every note on the topic. It is the one-paragraph answer to "what does the team now believe, and what is the evidence?"

**D.2 Connections map entry** (append to `notes/_connections.md`) — link patterns that span multiple categories:

```markdown
## <Pattern name>
- Links: <note 1 path>, <note 2 path>, <note 3 path>
- Pattern: <One sentence naming what is in common.>
- Implication: <What an agent should do differently given this connection.>
```

The map is read by every agent at planning time. Keep entries terse — the full reasoning lives in the linked notes.

**D.3 Open-questions entry** (append to `notes/_open-questions.md`) — gaps and contradictions:

```markdown
## <Question or contradiction>

**Claim A:** <note X says ...>
**Claim B:** <note Y says ...>
**Status:** unresolved | needs more data | resolved by note Z

(or, for a knowledge gap:)

## <Topic>: <what is missing>

**Status:** no experiments yet | partial | resolved
**Why it matters:** <cost of not knowing>
**Cheapest first experiment:** <one eval that would start to answer this>
```

---

## Filename Conventions

| Type | Pattern | Example |
|---|---|---|
| Experiment | `experiments/eval-<N>-<short-slug>.md` | `experiments/eval-12-simdeez-f.md` |
| Infra | `infra/<short-slug>.md` or `<short-slug>.md` | `infra/grader-mtime-drift.md` |
| Synthesis | `_synthesis/<topic>.md` | `_synthesis/simd-u8-widening.md` |
| Connections map | `_connections.md` (single file, append-only sections) | n/a |
| Open questions | `_open-questions.md` (single file, append-only sections) | n/a |
| Focus | `focus-<short-topic>.md` | `focus-1-agent-1-ivf-u8-simd.md` |
| Research | `research/<topic>/<short-slug>.md` | `research/simd/avx2-l2-distance.md` |
| Migration | `migration_<ISO-timestamp>_<agent_id>.md` | `migration_20260605T061159_0-agent-2.md` |

Rules:
- Lowercase, kebab-case, no spaces
- No agent id in the filename (except for `focus-*` and `migration_*`, which are inherently per-agent)
- No `notes.md` filename (legacy single-file format is not for new notes)
- Don't start filenames with `_` — that prefix is reserved for system-managed files

## Frontmatter (required for every note)

```yaml
---
creator: <your agent_id, from .coral_agent_id>
created: <ISO-8601 timestamp>
---
```

Add these when applicable:
- Experiment note: `commit: <coral eval hash>`
- Focus note: `generation: <int>` (bump on meaningful direction shift)

**Why frontmatter matters:** `creator:` is the only signal team-level processes have to attribute a note to an author. Notes without `creator:` are silently skipped by:
- `consolidate` heartbeat's team-audit step
- `librarian` subagent's note attribution
- Migration flows (a migrating agent's prior notes stay on the source island, but team-level views filter by author)

A note that does not name its author becomes invisible to the team's coordination layer. That is the highest-cost mistake you can make when writing a note — higher than any missing section.

## Self-Audit Checklist (run before saving)

Open the draft and verify each item. If any answer is "no" or "I don't know," fix the note before writing it. This is the step that distinguishes a useful note from a wall of headings.

**For all variants:**
- [ ] **Frontmatter is complete.** `creator:` is your agent_id, `created:` is ISO-8601.
- [ ] **Index updated.** A new one-line entry in `notes/index.md` under the right section.
- [ ] **Filepath uses kebab-case**, lowercase, no agent id (except for per-agent artifacts).

**For experiment (Variant A) and infra (Variant B) notes:**
- [ ] **Result has at least one absolute number AND at least one delta vs a baseline.** A result without a baseline is uninterpretable.
- [ ] **"What did not work" has ≥ 2 entries.** If you only tried one approach, say so explicitly and explain why you did not explore alternatives.
- [ ] **Every magic number has a source.** For each constant in the Mechanism section (bandwidth, latency, parameter values, thresholds), mark it as one of: **measured** (with the script/command that produced it), **cited** (with the paper / doc / file), or **estimated** (with a one-line justification). The default reading of an unsourced number is "the author guessed."
- [ ] **Cross-links exist.** If a `focus-*.md` exists for this direction, link it in Context and verify the abandon-if gate against your result. If a sister `experiments/*.md` note exists, link it in References.

**For experiment (Variant A) notes specifically:**
- [ ] **Every quantitative prediction in any prior note this builds on has been backfilled.** Open those notes, append "Predicted X, actual Y, gap = Z; mechanism was W," and link from this note's "Next" section. This is the rule `consolidate.md` implies but does not state explicitly.

**For synthesis (Variant D.1) notes:**
- [ ] **At least 3 attempt hashes are cited as evidence.**
- [ ] **A confidence level + conditions are stated.**
- [ ] **Counter-evidence is named**, even if "no counter-evidence found yet."

**For focus (Variant C) notes:**
- [ ] **Abandon-if gate is concrete and testable** (specific score / recall / failure mode, not a vibe).
- [ ] **Why-this-has-EV cites ≥ 1 other note or attempt.**
- [ ] **Posture is the most-missing one on the team**, not the most comfortable. Verify by `ls {shared_dir}/notes/focus-*.md` and reading the team roster in `_connections.md`.

## File-Writing Gotcha (read this — it will silently corrupt your note)

**Never write markdown content through `python3 -c "..."` or `echo` inside bash.** Bash sees backticks first and treats them as command substitution, replacing the backtick-delimited content with the (often empty) output of trying to execute it as a command. The Python `f.write(...)` then writes a string with all code blocks and inline code stripped. The `print('OK')` at the end runs fine, so the agent believes the note saved correctly.

Symptoms when this has happened:
- Code blocks (` ``` ... ``` `) are gone
- Inline code ( `` `path` ``, `` `variable` ``) is gone
- Adjacent prose reads as a fragment ("The binary at" / "already exists")
- bash stderr shows `command not found` for each backtick block

**Use one of these instead, in order of preference:**

1. **`coral notes write -` via stdin**, if available (does not exist yet — see "Open question" below).
2. **A heredoc with `<<'EOF'`** (single-quoted EOF disables shell expansion of `$`, backticks, and `\` inside the body):
   ```bash
   cat > .claude/notes/infra/grader-mtime.md <<'NOTE_EOF'
   ---
   creator: 0-agent-1
   ...
   NOTE_EOF
   ```
3. **The Write tool directly** with the file content as the parameter. This is the cleanest path for a moderate-sized note; the only limit is the tool's own input size.

Avoid:
- `python3 -c "..."` with markdown in the string
- `echo "..." > file.md` (same backtick problem, plus quoting issues)
- `printf "..." > file.md` (same)

If you must use `python3`, use a real script file (`Write` the script first, then `python3 script.py`), not `python3 -c`.

## Worked Example: Before and After

**Before** (the kind of note that shows up too often):

```markdown
# Grader infrastructure issues

## Issue 1: mtime

**Symptom:** Eval fails.

**Root cause:** The grader rebuilds the binary.

**Fix:** Touch the binary.

**Prevention:** Run the fix before every eval.
```

What is missing: the actual error message, the grader code path, the exact `touch` command, why the mtime drifts, what conditions trigger it, what other approaches were tried.

**After** (Variant B applied):

```markdown
---
creator: 0-agent-1
created: 2026-06-05T14:00:00+08:00
commit: n/a
---

# Grader infra: benchmark binary mtime drift after every eval

## Context
Mode: real (1M SIFT1M). Triggered when `examples/<task>/grader/benchmark/Cargo.toml`
mtime advances past `target/release/<bench-bin>` mtime, causing the grader to
attempt a rebuild that fails on `pkg-config` / `libssl-dev` not being installed.

## Result
| Eval | Mode | Outcome |
|---|---|---|
| #11 | real | FAILED: build (openssl-sys cannot find OpenSSL) |
| #11 (retry) | real | OK after `touch <bench-bin>` |

## Mechanism
Grader code path (see `grader/<task>/build.py`): the cached-binary check is
```python
if target.exists() and target.stat().st_mtime >= manifest.stat().st_mtime:
    return target
```
A second `cargo` operation in the worktree (other agents' worktree syncs, our
own `git status`, etc.) bumps `Cargo.toml` mtime and flips the comparison.
Then the rebuild runs into missing system deps.

## What did not work
- **`apt-get install libssl-dev pkg-config`** — sandbox is read-only / no sudo. Tried twice in attempt #10; permission denied both times.
- **`OPENSSL_DIR=<path>` env override** — openssl is not installed at all on the image, so the env var is a no-op.
- **Pinning reqwest to `rustls-tls`** — would need a `Cargo.toml` edit inside the grader benchmark, which the daemon's worktree sync overwrites within minutes.

## Surprises
- The mtime drift happens every 1-2 evals, not just when other agents commit. A single `coral eval` in our own worktree can be enough.
- The grader error message is misleading: it says "openssl not found" but the actual fix is unrelated to openssl.

## Next
1. **Add a `pre-eval` step in your workflow** that runs the `touch` command below. Cost: <100ms. Risk: none.
   ```bash
   touch examples/<task>/grader/benchmark/target/release/<bench-bin>
   ```
2. **Open a task-level fix**: change the grader's mtime check to use content-hash
   of the manifest instead of mtime, so worktree syncs don't trigger rebuilds.
   Post in the team's `_open-questions.md` so a future agent picks this up.
3. **Consider a setup step in `grader.setup`** that installs `libssl-dev` /
   `pkg-config` in the grader venv, so the rebuild path actually works. Same
   place to suggest.

## References
- attempt `b9c3c4c8`: FAILED eval with openssl-sys error (see `coral show b9c3c4c8`)
- attempt `5ec0a975`: OK eval after applying the `touch` workaround
- grader source: `examples/<task>/grader/build.py` (the mtime check)
- related: `_open-questions.md` → "Grader: mtime-based cache invalidation is fragile"
```

Notice the difference: the "after" version has a specific symptom (with the error text), a code citation, three rejected approaches (not just one), the actual `touch` command, and a follow-up to push the fix upstream — all things a future agent can act on without re-deriving the analysis.

## Open Questions / Known Gaps

- **No `coral notes write` CLI yet.** Heredoc / Write tool are the cleanest paths. If a `coral notes` subcommand that takes content from stdin is added, prefer it.
- **No enforcement of the variant templates.** A `coral notes lint` subcommand could parse existing notes and warn about missing sections / unsourced magic numbers / missing backfilled predictions. That is a future direction; for now the self-audit checklist above is on the agent.
- **Cross-island note sharing** is governed by the migration flow (a migrating agent carries their evolved role and cadence, but their prior notes stay on the source island). This skill is per-island.

## Quick Reference

| Need | Variant | Where it goes |
|---|---|---|
| Per-eval reflection | A | `notes/experiments/eval-<N>-<short-slug>.md` |
| Cross-eval pattern (e.g. "u8 SIMD works") | D.1 | `notes/_synthesis/<topic>.md` |
| Cross-category connection | D.2 | append to `notes/_connections.md` |
| Contradiction or knowledge gap | D.3 | append to `notes/_open-questions.md` |
| Grader / build / runtime issue | B | `notes/infra/<short-slug>.md` (or `notes/<slug>.md` if no `infra/`) |
| Agent's current direction + budget + abandon-if | C | `notes/focus-<topic>.md` |
| Index of all the above | — | Edit `notes/index.md` |

If a slot does not exist, create it — but check first with `ls {shared_dir}/notes/`.
