---
name: organize-files
description: "Organize the shared notes directory when it becomes hard to navigate. Restructure within research/ and experiments/, deduplicate, update index.md."
---

# Organize Files

Restructure the shared notes directory so every agent can find what they need quickly.

For a complete before/after walkthrough on a realistic messy notes/ tree — including the dedup pass, naming fixes, subdirectory creation, link repair, and audit-log entry — see [`references/worked-example.md`](references/worked-example.md). Read it once before your first reorganization; it makes the abstract steps below concrete.

For recovery procedures and judgment calls (move script aborted partway, false-positive duplicates, files that look misplaced in `_synthesis/`, contradicting `_open-questions.md`, races between agents…), see [`references/edge-cases.md`](references/edge-cases.md).

## When to Use

- Too many flat files in `research/` or `experiments/`
- Duplicate or near-duplicate notes
- Inconsistent naming (spaces, uppercase, agent IDs in filenames)
- After a deep-research or consolidate phase that created many files
- You can't find a note you know exists

## Notes Directory Structure

```
notes/
├── index.md          ← table of contents (research + experiments only)
├── raw/              ← immutable sources (DON'T touch)
├── research/         ← deep-research findings (organize within)
│   ├── <topic>/      ← group by topic or theme
│   └── ...
├── experiments/      ← eval reflections and results (organize within)
│   ├── <approach>/   ← group by approach or technique
│   └── ...
├── _synthesis/       ← consolidate owns this (DON'T touch)
├── _connections.md   ← consolidate owns this
├── _open-questions.md
└── _organization-log.md  ← append-only log of what you changed
```

## Process

### 1. Audit

Get the current state:

```bash
bash .coral/public/skills/organize-files/scripts/audit.sh
```

Or manually: `ls -R {shared_dir}/notes/` and count files per directory.

Also check for content-level issues:
- **Contradictions** — do any notes claim opposite things? Update or flag them in `_open-questions.md`.
- **Stale info** — research notes that experiments have disproven. Update with actual results.
- **Orphan pages** — notes not listed in `index.md`. Add them.
- **Missing cross-references** — related notes that don't link to each other.
- **Gaps** — techniques mentioned but never researched, or researched but never tried.

### 2. Plan

Write out your target structure before moving anything. Organize **within** `research/` and `experiments/` — add subdirectories by topic when a dir has 5+ files:

```
research/
├── algorithms/       (3+ notes)
├── optimization/     (3+ notes)
└── ...

experiments/
├── optimization/     (3+ notes)
├── debugging/        (3+ notes)
└── ...
```

Rules:
- **Minimum 3 files per subdirectory** — don't create a dir for 1-2 files
- **Max 2 levels deep** — `experiments/optimization/learning-rate.md` is the limit
- **Name by topic** — `algorithms/` not `agent1-work/`
- **Don't touch `raw/`** — immutable source material
- **Don't touch `_synthesis/`, `_connections.md`, `_open-questions.md`** — owned by consolidate

### 3. Deduplicate

Find near-duplicates:

```bash
python .coral/public/skills/organize-files/scripts/find_duplicates.py .coral/public/notes --threshold 0.5
```

For pairs above the threshold where the verdict is not immediately obvious from a quick read — same topic vs. different angle vs. different topic with shared boilerplate vs. genuinely contradicting — spawn the **Dedup Judge** subagent. It reads both notes blinded (no author / timestamp / length metadata) and returns a structured verdict (`same-topic-merge` / `different-angle-fold` / `contradicting-do-not-merge` / `keep-both-rename`) with concrete merge or rename instructions. See [`agents/dedup-judge.md`](agents/dedup-judge.md). Use it especially when:

- The two notes were written by different agents (recency / author bias is highest).
- One note is much longer than the other (length bias makes the long one feel authoritative).
- The notes appear to disagree but you can't tell if it's a real conflict or a scope difference.

For obvious cases — verbatim duplicates, or clearly different topics that shared a paragraph — just decide directly.

When merging confirmed duplicates, **preserve provenance from both notes** — never just pick one and discard:

- **Union the `## References` lists** (de-duplicated by URL or `raw/` filename). Losing a citation loses an audit trail that an agent may need months later.
- **Keep the more specific claims from each note**, not just whichever was longer. A short note with concrete numbers usually has higher information density than a long one with vague prose.
- **Combine `tags` and `aliases`** rather than picking one set. Both were correct in their original context.

Move originals to `_archive/` so the merge is reversible.

When two notes **contradict** each other, don't merge:

- Flag the conflict in `_open-questions.md` (existing rule).
- Also stamp `contradictedBy: [other-note-slug]` into each note's frontmatter so future readers see the conflict at the note level — `_open-questions.md` collects them, but agents reading the note directly should see the warning without a separate lookup.

### 4. Move and Rename

Use the move script for safe moves with frontmatter tracking:

```bash
python .coral/public/skills/organize-files/scripts/move_note.py SOURCE DEST
```

Naming: `kebab-case-like-this.md`, topic first, no agent IDs, no bare dates, under 60 chars.

### 5. Update Index

Regenerate `index.md`:

```bash
python .coral/public/skills/organize-files/scripts/generate_index.py .coral/public/notes
```

The index should only list `research/` and `experiments/` entries — not `raw/`.

Then resolve cross-links — moves and renames break any `[[old-slug]]` references in note bodies:

```bash
python .coral/public/skills/organize-files/scripts/resolve_links.py .coral/public/notes --dry-run
# review the diff, then:
python .coral/public/skills/organize-files/scripts/resolve_links.py .coral/public/notes
```

The resolver walks every note, scans the body for plain-text mentions of every other note's title, and wraps them as `[[slug|Title]]`. It skips text already inside wikilinks, citation markers, code blocks, and inline code. Run this **after** moves and renames, not before — the resolver needs final paths.

### 6. Log

Append a summary to `_organization-log.md`: what you moved, merged, or renamed, and why.
