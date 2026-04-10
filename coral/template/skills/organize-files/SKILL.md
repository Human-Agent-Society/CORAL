---
name: organize-files
description: Organize the shared notes directory when it becomes hard to navigate. Use when there are >10 flat files in notes/, when you see duplicate or near-duplicate titles, when you see meaningless titles, when naming is inconsistent (spaces, uppercase, agent IDs in filenames), when you can't find a note you're looking for, when you don't know where to save a new note, or after a consolidate or warmstart that brought in many files at once. Also use for post-consolidation structural cleanup.
---

# Organize Files

Restructure the shared notes directory so every agent can find what they need quickly. This skill handles **structural organization** — renaming, moving, deduplicating, and indexing files. It complements the `consolidate` heartbeat, which handles **knowledge synthesis** (creating `_synthesis/` documents, `_connections.md`, and `_open-questions.md`).

**Core loop:** `audit → categorize → restructure → deduplicate → index → verify`

The goal is findability. A well-organized notes directory means agents spend less time searching and more time experimenting. Notes that are easy to find get read; notes buried in a flat list of 90+ files get ignored.

---

## 1. When to Trigger

### Proactive Triggers

Use this skill when you notice any of:

- **>10 flat `.md` files** in the top level of `notes/` — a flat list this large is hard to scan
- **3+ files with similar titles** — likely duplicates or near-duplicates that should be merged
- **Inconsistent naming** — spaces in filenames, uppercase, agent IDs (`agent1-reflection-12.md`), bare dates (`2026-03-15.md`)
- **Post-consolidate cleanup** — after `consolidate` creates synthesis documents, the source notes often benefit from reorganization
- **Post-warmstart** — when a new run inherits notes from a previous run, they may need reorganization for the new context

### Reactive Triggers

- You **can't find a note** you know exists — the structure isn't working
- You **don't know where to save** a new note — the categories aren't clear
- Another agent asks where something is or reports difficulty finding information

---

## 2. Audit Phase

Start every organization effort with an audit to understand the current state.

### Quick Automated Audit

Run the audit script for a fast overview:

```bash
bash scripts/audit.sh
```

This shows file count, directory structure, naming issues, recent activity, and creator distribution. It's read-only — it never modifies files.

If `scripts/audit.sh` is not available in your current directory, find it in the skill directory:

```bash
bash .coral/public/skills/organize-files/scripts/audit.sh
```

### Manual Assessment

After the automated audit, manually assess:

1. **Thematic clusters** — group files mentally by topic. Which topics have 3+ notes?
2. **Naming patterns** — which names are descriptive? Which are meaningless (`results.md`, `notes.md`)?
3. **Staleness** — are there notes from early in the run that have been superseded by newer findings?
4. **Duplication** — do multiple notes cover the same ground?

### Write Audit Summary

Record your assessment in `_organization-log.md` (append-only):

```markdown
## Audit — [date]

- Total notes: 47
- Top-level: 38 (too many)
- Naming issues: 12 files with agent IDs, 5 with spaces
- Thematic clusters identified: optimization (14), architecture (9), debugging (7), strategy (5), uncategorized (12)
- Duplicates suspected: 3 pairs
- Plan: Create 4 subdirectories, rename 12 files, investigate 3 duplicate pairs
```

---

## 3. Categorization Strategy

Categories should **emerge from the content** of your notes, not be imposed from a template. The taxonomy in `references/category-taxonomy.md` is a starting point — read it for inspiration, then adapt.

### Principles

- **Minimum 3 notes per subdirectory** — don't create a directory for 1-2 files
- **Name by topic, not agent or date** — `optimization/` not `agent1-work/` or `march-notes/`
- **Broad categories first** — start with 3-5 top-level directories, add subcategories only when a directory has 5+ notes on distinct subtopics
- **Maximum 2 levels deep** — `optimization/learning-rate/warmup-findings.md` is the limit. Deeper nesting makes paths unwieldy

### Category Planning

Before moving any files, write out your planned structure:

```
notes/
├── architecture/        (9 notes)
├── optimization/        (14 notes)
│   ├── learning-rate/   (6 notes)
│   └── regularization/  (4 notes)
├── debugging/           (7 notes)
├── strategy/            (5 notes)
├── [top-level]          (12 notes — leave uncategorized for now)
├── _synthesis/          (existing, don't touch)
├── _index.md
└── _organization-log.md
```

---

## 4. Directory Hierarchy

### Example Target Structure

```
notes/
├── architecture/
│   ├── attention-mechanism-findings.md
│   ├── layer-depth-comparison.md
│   └── normalization-strategy.md
├── optimization/
│   ├── learning-rate/
│   │   ├── warmup-schedule-results.md
│   │   └── cosine-decay-analysis.md
│   └── batch-size-effects.md
├── debugging/
│   ├── gradient-clipping-investigation.md
│   └── nan-loss-root-cause.md
├── strategy/
│   ├── next-experiments-priority.md
│   └── architecture-vs-hyperparameter-focus.md
├── _synthesis/                    # consolidate owns this
├── _archive/                      # superseded originals
├── _index.md                      # auto-generated
├── _organization-log.md           # append-only log
├── _connections.md                # consolidate owns this
└── _open-questions.md             # consolidate owns this
```

### Rules

- **Underscore-prefixed items are reserved for meta** — `_index.md`, `_archive/`, `_organization-log.md`, `_synthesis/`, etc.
- **Don't nest beyond 2 levels** — if you need a third level, the second level is probably too narrow
- **Minimum 3 files per subdirectory** — if a subdirectory would have fewer, keep those files in the parent

---

## 5. Naming Conventions

Use kebab-case, topic-first names under 60 characters. For detailed rules and transformation examples, read `references/naming-conventions.md`.

**Quick rules:**
- `kebab-case-like-this.md` — lowercase, hyphens, `.md` extension
- Topic first: `gradient-clipping-results.md` not `results-gradient-clipping.md`
- No agent IDs: authorship lives in the `creator` frontmatter field
- No bare dates: dates live in the `created` frontmatter field
- Under 60 characters: long names get truncated and are hard to reference

---

## 6. Restructuring

### Using the Move Script

For safe moves with automatic frontmatter tracking:

```bash
python scripts/move_note.py SOURCE DEST
```

Or from the skill directory:

```bash
python .coral/public/skills/organize-files/scripts/move_note.py notes/old-name.md notes/optimization/new-name.md
```

The script:
- Refuses files modified <5 minutes ago (override with `--force`)
- Creates parent directories automatically
- Adds `moved_from`/`renamed_from` and `moved_at` to frontmatter
- Writes to destination first, verifies, then deletes source
- Supports `--dry-run` to preview changes

### Batch Operations

When reorganizing many files:

1. **Plan all moves first** — write the full list of source → destination pairs
2. **Dry-run the batch** — run each move with `--dry-run` to check for conflicts
3. **Execute the batch** — run the moves
4. **Verify** — check that all files landed in the right place

### Manual Moves

If the script isn't available, you can move files manually. Remember to:
- Create directories with `mkdir -p` before moving
- Add `moved_from` and `moved_at` to the frontmatter of moved files
- Write first, verify, then delete the source

---

## 7. Deduplication

### Finding Duplicates

Run the duplicate finder:

```bash
python scripts/find_duplicates.py
```

Or from the skill directory:

```bash
python .coral/public/skills/organize-files/scripts/find_duplicates.py .coral/public/notes --threshold 0.5
```

This compares all note pairs using weighted Jaccard similarity on titles (60%) and first paragraphs (40%). Pairs above the threshold are reported with similarity scores.

Use `--json` for machine-readable output. Adjust `--threshold` (0.0–1.0) to be more or less aggressive.

### Merging Procedure

When you confirm two notes are genuine duplicates:

1. **Create the merged note** with the combined content. Preserve the most complete version as the base and integrate unique content from the other
2. **Set frontmatter** on the merged note:
   - `creator`: list all original creators
   - `created`: use the earliest date
   - `merged_from`: list original filenames
3. **Move originals to `_archive/`** — don't delete them. Archived files preserve full provenance
4. **Log the merge** in `_organization-log.md`

### What NOT to Merge

- Notes that **contradict each other** — these represent different findings, not duplicates. Mark the contradiction in `_open-questions.md` instead
- Notes from **different stages** of investigation — an early hypothesis and a later conclusion may look similar but serve different purposes
- Notes with **different audiences** — a technical deep-dive and a summary for strategy may cover the same topic at different levels

---

## 8. Index Generation

After restructuring, generate a navigable index:

```bash
python scripts/generate_index.py
```

Or from the skill directory:

```bash
python .coral/public/skills/organize-files/scripts/generate_index.py .coral/public/notes
```

This creates `_index.md` with a table of contents grouped by directory, showing title, creator, and date for each note. The index:

- Uses atomic writes (temp file + `os.replace`) — safe for concurrent access
- Excludes underscore-prefixed meta files from the listing
- Is idempotent — same input produces the same output
- Supports `--dry-run` to preview without writing

Run the index generator after every reorganization to keep it current.

---

## 9. Metadata Preservation

Organization must preserve provenance. The scripts handle most tracking automatically, but keep these rules in mind for manual operations.

### During Moves/Renames

The `move_note.py` script automatically adds:
- `moved_from: <original path>` (for moves between directories)
- `renamed_from: <original filename>` (for renames within the same directory)
- `moved_at: <ISO timestamp>`

### During Merges

Manually add to the merged note's frontmatter:
- `created`: use the **earliest** date from all originals
- `creator`: list **all** original creators
- `merged_from`: list original filenames as a YAML list

### Critical Safety Rules

- **Never modify `creator` or `created`** during moves — these track the original author and time
- **Never delete originals during merges** — move them to `_archive/` instead
- **Always verify writes** before deleting sources — the move script does this automatically

---

## 10. Conflict-Free Operation

Multiple agents may be working simultaneously. These rules prevent conflicts:

### Age Gate

The `move_note.py` script refuses to move files modified less than 5 minutes ago. This prevents moving a file another agent is actively writing. Use `--force` only when you're certain no one else is editing the file.

### Write-First-Delete-Second

The move script always writes the complete file to the destination and verifies the write before deleting the source. If the write fails, the source remains untouched.

### Directory Safety

Always use `mkdir -p` when creating directories — it's idempotent and won't fail if the directory already exists (another agent may have created it).

### Append-Only Logging

`_organization-log.md` is append-only. Never edit or truncate previous entries — other agents may reference them.

### Don't Modify Consolidate's Artifacts

The `consolidate` heartbeat owns these files. Do not modify or reorganize them:
- `_synthesis/` directory and its contents
- `_connections.md`
- `_open-questions.md`

You may move regular notes *into* subdirectories that consolidate references, but don't move or rename the consolidate artifacts themselves.

---

## 11. Integration with Consolidate and Reflect

These three features form a pipeline:

```
reflect (content creation) → consolidate (knowledge synthesis) → organize-files (structural organization)
```

### Division of Labor

| Feature | Purpose | Artifacts |
|---------|---------|-----------|
| `reflect` | Create new notes from experiment results | Individual `.md` notes |
| `consolidate` | Synthesize knowledge across notes | `_synthesis/`, `_connections.md`, `_open-questions.md` |
| `organize-files` | Restructure for findability | Subdirectories, `_index.md`, `_archive/` |

### Recommended Workflow

1. Agents **reflect** after experiments → notes accumulate
2. Periodically **consolidate** → synthesis documents appear
3. When notes are hard to navigate → **organize-files** → clean structure
4. Repeat as notes continue to grow

### Optional Heartbeat Integration

To run organization periodically, add to the heartbeat configuration:

```yaml
heartbeat:
  actions:
    - type: organize
      interval: 30  # minutes
```

Or trigger manually when you notice the notes directory is hard to navigate.

---

## 12. Quick Reference Checklist

For repeat use — the compact version of this skill:

1. Run `bash scripts/audit.sh` — understand current state
2. Identify thematic clusters — group mentally by topic
4. Plan directory structure — 3-5 top-level categories, min 3 files each
5. Run `python scripts/find_duplicates.py` — check for near-duplicates
6. Merge confirmed duplicates — originals to `_archive/`
7. Move files with `python scripts/move_note.py` — frontmatter tracked automatically
8. Rename poorly-named files — see `references/naming-conventions.md`
9. Run `python scripts/generate_index.py` — create `_index.md`
10. Append summary to `_organization-log.md` — record what you did and why
