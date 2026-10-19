---
name: scan-usage
description: "Measure which shared notes and skills agents actually read by scanning agent session logs. Use before archiving, merging, or retiring knowledge — curation decisions should be based on usage evidence, not guesses."
---

# Scan Usage

Answer "is anyone actually reading this?" with evidence from agent session
logs, instead of asking agents to self-report or guessing from file age.

## When to Use

- Before archiving or deleting a note — check nobody depends on it
- Before retiring or rewriting a skill — check whether it is ever invoked
- Deciding which notes to consolidate first (heavily-read ones pay off most)
- Checking whether a skill you built is being discovered by other agents
- During a librarian audit, to rank the knowledge base by real consumption

## Usage

```bash
# Full report: per-skill uses, per-note reads/writes, never-read inventory
python .claude/skills/scan-usage/scripts/scan_usage.py

# Machine-readable, for filtering with jq or python
python .claude/skills/scan-usage/scripts/scan_usage.py --json

# One agent's reading habits
python .claude/skills/scan-usage/scripts/scan_usage.py --agent agent-2
```

The script reads `.claude/logs/*.log` (every agent's session log, NDJSON)
and counts agent-initiated tool calls touching `notes/` and `skills/`:

| Signal | Counted as |
|---|---|
| `Read` of `notes/<path>.md` | note read |
| `cat` / `sed` / `grep` a specific note file in Bash | note read |
| `Write` / `Edit` of a note | note write (authorship, not consumption) |
| `Glob` / `Grep` patterns under `notes/` | browse (discovery only) |
| `Skill` tool invocation | skill use |
| Reading or running anything under `skills/<name>/` | skill use |
| `coral skills --read <name>` | skill use |

It then diffs against what exists on disk and lists **never-read notes**
and **never-used skills**. It never modifies files.

## Interpreting the Numbers

- **High reads + many distinct readers** — load-bearing knowledge. Keep it
  authoritative: merge duplicates *into* it, keep its path stable, improve
  it rather than fragmenting.
- **Writes but zero reads by others** — the author is talking to themselves.
  Candidate for merging into a hub note, or its title/index entry needs to
  be more discoverable.
- **Never read / never used** — retirement candidate, but apply an
  **evidence floor**: low counts early in a run mean "not yet", not
  "useless". Only archive when the run has accumulated enough activity
  (many evals since the file was created) and the count is still zero.
  Archive (move to `notes/_archive/`), don't delete — archiving is
  reversible via checkpoint history, premature deletion is how useful
  knowledge gets destroyed.
- **A skill with uses concentrated in its author** — the description in its
  SKILL.md frontmatter probably doesn't trigger for anyone else; rewrite it.

## Known Blind Spots

- **Subagent activity is invisible.** Tool calls made inside spawned
  subagents (deep-researcher, librarian) only appear in logs as progress
  events without file paths, so their reads are not counted. Reads from the
  main agent loop dominate in practice.
- `coral notes --read N` is index-based; those reads are counted in
  aggregate but can't be attributed to a specific note (reported separately).
- Logs only cover this run (and this island, in multi-island mode). A note
  seeded from a warm start may look unread here yet have earned its place
  in a previous run.
