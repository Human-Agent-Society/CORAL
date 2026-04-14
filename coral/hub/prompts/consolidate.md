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

---
The goal is knowledge creation: every consolidation should leave the knowledge base smarter than before.
After consolidating, resume optimizing.
