## Heartbeat: Knowledge Synthesis

Pause your current work and synthesize the shared knowledge base. Your goal is to **create or update knowledge artifacts** — not just reorganize files.

### Required outputs

By the end of this consolidation, you should have created or updated at least one of:

1. **A synthesis note** in `notes/_synthesis/` — distill multiple related notes into unified findings
2. **The connections map** at `notes/_connections.md` — document patterns that span categories
3. **The open questions list** at `notes/_open-questions.md` — gaps and unresolved contradictions

### Process

**Step 1: Read and absorb**

Browse `{shared_dir}/notes/` and read notes you haven't seen or that have been updated. Build a mental map of what's known.

**Step 2: Synthesize findings**

For any topic with 3+ notes, create or update a synthesis note:

```
notes/_synthesis/
  learning-rate-findings.md    # "Based on 12 experiments, warmup helps when batch > 64..."
  regularization-patterns.md   # "Dropout vs weight decay: use dropout for large models..."
  architecture-lessons.md      # "Attention > convolution for sequence tasks because..."
```

A good synthesis note:
- States the conclusion upfront
- Cites specific attempts/notes as evidence
- Explains *why* something works, not just *that* it works
- Notes confidence level and conditions where it applies

*Example:*
```markdown
# Learning Rate Findings

**Summary:** Warmup is critical for batch sizes > 64. Linear warmup for 5-10% of training works best.

**Evidence:**
- attempt abc123: No warmup with batch=128 → diverged
- attempt def456: 5% warmup with batch=128 → stable, 0.82 score
- attempt ghi789: 10% warmup with batch=64 → no difference vs no warmup

**Why it works:** Large batches have higher gradient variance in early training...

**Confidence:** High for batch > 64, uncertain for smaller batches.
```

**Step 3: Map connections**

Update `notes/_connections.md` with cross-category patterns:

```markdown
# Knowledge Connections

## Gradient scale sensitivity
- Links: `optimization/learning-rate/`, `debugging/gradient-clipping.md`, `architecture/normalization/`
- Pattern: Many issues trace back to gradient magnitude. When something breaks, check gradient norms first.

## Model capacity vs regularization
- Links: `architecture/model-size.md`, `optimization/regularization/`
- Pattern: Larger models need less regularization. Dropout hurts small models.
```

**Step 4: Document contradictions and gaps**

Update `notes/_open-questions.md`:

```markdown
# Open Questions

## Unresolved contradictions
- Dropout: helps in note A (large model), hurts in note B (small model). Need to test threshold.

## Knowledge gaps
- No experiments yet on: mixed precision training, gradient accumulation
- Uncertain: optimal warmup for batch < 32

## Next experiments to try
- Test dropout with model sizes 1M, 10M, 100M params to find threshold
```

**Step 5: Organize structure (if needed)**

If the notes folder is disorganized (too many flat files, duplicates, naming issues), use the `organize-files` skill to restructure it:

```
bash {shared_dir}/skills/organize-files/scripts/audit.sh
```

If the audit shows problems, follow the full process in `{shared_dir}/skills/organize-files/SKILL.md`. The skill provides scripts for deduplication, safe moves with frontmatter tracking, and index regeneration. Only reorganize within `research/` and `experiments/` — don't touch `raw/`, `_synthesis/`, or `_connections.md`.

**Step 6: Extract skills**

If a synthesis reveals a well-validated, reusable technique, promote it to `{shared_dir}/skills/`. Follow `skill-creator/SKILL.md`.

**Step 7: Audit the team's roles, lanes, and postures**

Read every agent's role file (`ls {shared_dir}/roles/*.md`) and every active focus note (`ls {shared_dir}/notes/focus-*.md`). Produce a one-paragraph roster summary, either in `{shared_dir}/notes/_connections.md` or as a dated entry in `{shared_dir}/notes/_synthesis/team-roster.md`. The summary should answer:

- **Role coverage** — quote each agent's current role description (one line each) and their generation number. Stable, high-generation, evidence-backed role files are signals of committed specialization. Generation-0 or all-aspirational role files after many evals are signals an agent hasn't found their footing — useful information for the team.
- **Lane coverage** — what techniques/areas are currently in flight (from focus notes)? Are two or more agents on the same lane? Are there obvious unexplored lanes from `_open-questions.md` that nobody is working on?
- **Posture coverage** — synthesizing across roles and focus notes, which functional roles (engineer / researcher / performance engineer / tooling engineer / reviewer / tech writer, or invented variants) are filled, and which are absent? An all-engineer team is a warning sign, especially if scores have plateaued.
- **Stale focus notes** — any focus note whose creator hasn't submitted an eval in the last several heartbeats is probably abandoned. Flag it (or delete it if the creator has clearly moved on).

This roster is read by every agent at planning time. Keeping it accurate is what makes complementary lane/posture choice possible without anyone being assigned a role.

Do **not** edit other agents' role files as part of this audit — those are owned by their authors. The roster is a third-person summary of what the role files already say.

---
The goal is knowledge creation: every consolidation should leave the knowledge base smarter than before.

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

After consolidating, resume optimizing.
