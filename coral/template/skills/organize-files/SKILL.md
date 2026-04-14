---
name: organize-files
description: "Organize the shared notes directory when it becomes hard to navigate. Restructure within research/ and experiments/, deduplicate, update index.md."
---

# Organize Files

Restructure the shared notes directory so every agent can find what they need quickly.

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

Merge confirmed duplicates. Move originals to `_archive/`. Don't merge notes that contradict each other — flag those in `_open-questions.md`.

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

### 6. Log

Append a summary to `_organization-log.md`: what you moved, merged, or renamed, and why.
