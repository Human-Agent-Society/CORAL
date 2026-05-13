# Worked Example — A Real Reorganization

A concrete before/after walkthrough. Use this as a model for your own reorganizations: audit, plan on paper, execute, log.

---

## The Mess (before)

After three deep-research sessions and one consolidation run, `notes/` looks like this:

```
notes/
├── index.md                      ← outdated, missing 4 files
├── raw/
│   ├── attention-is-all-you-need.md
│   ├── flash-attention-paper.md
│   ├── lora-paper.md
│   └── ... (12 more)
├── research/
│   ├── Attention Mechanisms.md           ← spaces + uppercase
│   ├── attention_in_transformers.md      ← snake_case
│   ├── attention-mechanisms-v2.md        ← duplicate of #1, by another agent
│   ├── flash-attention.md
│   ├── lora.md
│   ├── lora-fine-tuning.md               ← near-duplicate of lora.md
│   ├── prefix-tuning.md
│   ├── adapter-tuning.md
│   ├── sparse-attention.md
│   ├── gradient_checkpointing.md         ← snake_case again
│   ├── memory-tricks.md                  ← orphan, not in index
│   ├── debugging-OOM.md                  ← uppercase
│   └── agent3-notes.md                   ← agent ID in filename
├── experiments/
│   ├── exp-001.md
│   ├── exp-002.md
│   ├── exp-003.md
│   └── ... (8 more, all named exp-NNN)
└── _open-questions.md
```

Issues, in priority order:
1. **Two pairs of near-duplicates** in `research/`.
2. **Inconsistent naming** — spaces, uppercase, snake_case, agent ID.
3. **Two orphan files** not listed in `index.md`.
4. **Both `research/` and `experiments/` are flat** — 13 and 11 files respectively, well past the 5-file threshold for adding subdirectories.
5. **`exp-NNN` naming** in experiments hides what each one is actually about.

---

## The Plan (on paper, before any moves)

```
research/
├── attention/                    (4 notes — group existing attention work)
│   ├── attention-mechanisms.md   ← merged from "Attention Mechanisms.md" + attention_in_transformers.md + attention-mechanisms-v2.md
│   ├── flash-attention.md
│   ├── sparse-attention.md
│   └── attention-survey.md       (rename from agent3-notes.md after reading content)
│
├── peft/                         (4 notes — parameter-efficient fine-tuning)
│   ├── lora.md                   ← merged from lora.md + lora-fine-tuning.md
│   ├── prefix-tuning.md
│   ├── adapter-tuning.md
│   └── peft-comparison.md        (new — derived from above; create only if synthesis exists)
│
└── memory/                       (3 notes — memory + debugging)
    ├── gradient-checkpointing.md (rename from snake_case)
    ├── memory-tricks.md
    └── debugging-oom.md          (lowercase)

experiments/
├── attention/                    (rename exp-NNN by topic after reading each)
│   ├── flash-attention-baseline.md
│   ├── sparse-attention-sweep.md
│   └── attention-context-length.md
└── peft/
    ├── lora-rank-sweep.md
    ├── adapter-bottleneck-sweep.md
    └── ... (rest renamed by reading content)
```

Rules applied:
- Subdirectories only where ≥3 files justify them.
- All names kebab-case, lowercase, no agent IDs.
- Two-level depth max.

---

## Execution

### Pre-flight check

```bash
bash .coral/public/skills/organize-files/scripts/audit.sh notes/
# Confirms: 24 files, 7 with naming issues, 2 not in index
```

### Deduplicate (do this first — moves are wasted on files about to be merged)

```bash
python .coral/public/skills/organize-files/scripts/find_duplicates.py notes/ --threshold 0.5
# Output (paraphrased):
#   research/Attention Mechanisms.md  ↔  research/attention_in_transformers.md     0.78
#   research/Attention Mechanisms.md  ↔  research/attention-mechanisms-v2.md       0.81
#   research/lora.md                  ↔  research/lora-fine-tuning.md              0.66
```

Read all six files. The three `attention*` files cover the same ground from slightly different angles — merge into one. The two `lora*` files are largely the same with a few extra benchmarks in `lora-fine-tuning.md` — merge into `lora.md`.

For each merge, follow SKILL.md step 3 rules: union References, keep the more specific claims from each, combine tags, archive originals.

```bash
# After manually creating the merged content:
mkdir -p notes/_archive
mv "notes/research/Attention Mechanisms.md" notes/_archive/
mv notes/research/attention_in_transformers.md notes/_archive/
mv notes/research/attention-mechanisms-v2.md notes/_archive/
mv notes/research/lora-fine-tuning.md notes/_archive/
# Write the merged research/attention-mechanisms.md and research/lora.md
```

### Read the obscurely-named files before moving

```bash
# What's in agent3-notes.md and exp-001.md..exp-011.md?
head -20 notes/research/agent3-notes.md
for f in notes/experiments/exp-*.md; do
  echo "=== $f ==="
  grep -m 1 '^title:\|^# ' "$f"
done
```

This is the step that's easy to skip and easy to regret. Naming a file by topic requires knowing what's in it.

### Create subdirs and move

```bash
mkdir -p notes/research/{attention,peft,memory}
mkdir -p notes/experiments/{attention,peft}

# Use move_note.py — it preserves frontmatter trail
python .coral/public/skills/organize-files/scripts/move_note.py \
    notes/research/attention-mechanisms.md notes/research/attention/attention-mechanisms.md
python .coral/public/skills/organize-files/scripts/move_note.py \
    notes/research/flash-attention.md notes/research/attention/flash-attention.md
# ... repeat for each file ...
```

Always go through `move_note.py`, not bare `mv` — the script appends a moved-from entry to the file's frontmatter so cross-references can be repaired later.

### Resolve broken cross-links

After moves, any `[[old-slug]]` references in note bodies are broken. Run the link resolver:

```bash
python .coral/public/skills/organize-files/scripts/resolve_links.py notes/ --dry-run
# Review the diff, then:
python .coral/public/skills/organize-files/scripts/resolve_links.py notes/
```

### Regenerate the index

```bash
python .coral/public/skills/organize-files/scripts/generate_index.py notes/
```

### Log

```bash
cat >> notes/_organization-log.md <<'EOF'

## 2026-05-09 — attention/peft/memory restructure (agent: <id>)

- Merged 3 attention notes → research/attention/attention-mechanisms.md (originals → _archive/)
- Merged 2 lora notes → research/peft/lora.md (originals → _archive/)
- Created subdirs: research/{attention,peft,memory}, experiments/{attention,peft}
- Renamed exp-NNN files by topic after reading each
- Renamed agent3-notes.md → research/attention/attention-survey.md
- Fixed naming on 4 files (spaces, uppercase, snake_case → kebab-case)
- Resolved 12 broken [[wikilinks]] via resolve_links.py
- Regenerated index.md
EOF
```

---

## After

```
notes/
├── index.md                              ← regenerated, all 19 files listed
├── raw/                                  ← untouched
├── research/
│   ├── attention/
│   │   ├── attention-mechanisms.md       (merged)
│   │   ├── attention-survey.md           (was agent3-notes.md)
│   │   ├── flash-attention.md
│   │   └── sparse-attention.md
│   ├── memory/
│   │   ├── debugging-oom.md
│   │   ├── gradient-checkpointing.md
│   │   └── memory-tricks.md
│   └── peft/
│       ├── adapter-tuning.md
│       ├── lora.md                       (merged)
│       └── prefix-tuning.md
├── experiments/
│   ├── attention/
│   │   ├── attention-context-length.md
│   │   ├── flash-attention-baseline.md
│   │   └── sparse-attention-sweep.md
│   └── peft/
│       ├── adapter-bottleneck-sweep.md
│       ├── lora-rank-sweep.md
│       └── ... (renamed)
├── _archive/                             (5 superseded files)
├── _open-questions.md
└── _organization-log.md                  (entry appended)
```

Net: 24 files → 19 (5 merged into 2). All names consistent. Index regenerated. Two-level hierarchy. Cross-links repaired. Audit trail preserved in `_archive/` and `_organization-log.md`.

## Rules embedded in this example

- **Dedup before moving.** Moving a file you're about to delete wastes work and confuses the move log.
- **Read before renaming.** Topic-based names require knowing the topic.
- **Always use `move_note.py`.** Bare `mv` loses the moved-from breadcrumb.
- **Resolve links last.** Move first, then re-link — the resolver needs final paths.
- **Log everything.** `_organization-log.md` is what lets the next agent understand why the structure looks the way it does.
