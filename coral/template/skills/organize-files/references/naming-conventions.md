# Naming Conventions

Rules and examples for naming notes, directories, and tracking moves. Read this when deciding how to name or rename files during organization.

---

## Core Rules

1. **kebab-case** — lowercase words separated by hyphens: `learning-rate-findings.md`
2. **Topic-first** — lead with the subject, not the agent or date: `gradient-clipping-results.md` not `agent2-results-march.md`
3. **No agent IDs** — the `creator` frontmatter field tracks authorship. File names like `agent1-reflection-12.md` lose meaning after reorganization
4. **No bare dates** — dates belong in frontmatter `created` field. If a date is essential to the topic, put it after: `training-run-2026-03-15.md`
5. **Under 60 characters** — long names get truncated in terminals and are harder to reference
6. **Descriptive nouns** — prefer nouns over verbs: `batch-size-analysis.md` not `analyzing-batch-sizes.md`

## Transformation Examples

| Before | After | Why |
|--------|-------|-----|
| `agent1-reflection-12.md` | `attention-layer-findings.md` | Topic-first, remove agent ID |
| `results.md` | `dropout-regularization-results.md` | Add topic specificity |
| `IMPORTANT_NOTES.md` | `gradient-stability-notes.md` | Lowercase kebab-case, add topic |
| `2026-03-15-experiment.md` | `mixed-precision-experiment.md` | Topic-first, date in frontmatter |
| `my notes on lr.md` | `learning-rate-warmup.md` | Remove spaces, expand abbreviation |
| `debug_stuff.md` | `nan-loss-debugging.md` | Specific topic, kebab-case |
| `Agent 3 - Try #5.md` | `residual-connection-depth.md` | Topic-first, remove agent ID and trial number |
| `untitled.md` | `weight-initialization-comparison.md` | Descriptive name from content |
| `todo.md` | `next-experiments-architecture.md` | Specific topic |
| `notes_about_the_optimizer_learning_rate_schedule_warmup_and_decay.md` | `lr-schedule-warmup-decay.md` | Under 60 chars |

## Directory Naming

- **Singular nouns**: `architecture/` not `architectures/`
- **Match specificity to hierarchy level**: top-level broad (`optimization/`), second-level specific (`learning-rate/`)
- **kebab-case** applies to directories too
- **No nesting beyond 2 levels**: `optimization/learning-rate/warmup-findings.md` is the maximum depth

## Reserved Names

These underscore-prefixed names have special meaning and should not be used for regular notes:

| Name | Purpose | Owner |
|------|---------|-------|
| `_index.md` | Auto-generated table of contents | `organize-files` skill |
| `_organization-log.md` | Append-only log of organization actions | `organize-files` skill |
| `_synthesis/` | Synthesized knowledge documents | `consolidate` heartbeat |
| `_connections.md` | Cross-category pattern map | `consolidate` heartbeat |
| `_open-questions.md` | Gaps and contradictions | `consolidate` heartbeat |
| `_archive/` | Superseded originals after merges | `organize-files` skill |

## Frontmatter Tracking Fields

When files are moved or merged, add these fields to preserve provenance:

| Field | When to Add | Example |
|-------|-------------|---------|
| `moved_from` | File moved to a different directory | `moved_from: optimization/old-lr-notes.md` |
| `renamed_from` | File renamed in the same directory | `renamed_from: results.md` |
| `merged_from` | File created by merging others | `merged_from: [lr-notes-1.md, lr-notes-2.md]` |
| `moved_at` | Timestamp of the move/rename | `moved_at: 2026-03-15T14:30:00+00:00` |

The `move_note.py` script adds `moved_from`/`renamed_from` and `moved_at` automatically. For manual merges, add `merged_from` by hand.
