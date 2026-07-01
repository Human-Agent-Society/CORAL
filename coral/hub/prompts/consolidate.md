## Heartbeat: Knowledge Synthesis

Pause your current work and synthesize the shared knowledge base. Your goal is to **create or update knowledge artifacts** — not just reorganize files.

The `create-notes` skill (`{shared_dir}/skills/create-notes/SKILL.md`) provides the formats and self-audit checklist for all three output types below. Read it before writing. The most relevant sections are:

- **Variant D.1** — synthesis note format
- **Variant D.2** — connections map entry format
- **Variant D.3** — open-questions entry format
- **Frontmatter discipline** — the `creator:` field is required; team-level processes silently skip notes without it

The skill covers the mechanics; this prompt covers the process.

### Required outputs

By the end of this consolidation, you should have created or updated at least one of:

1. **A synthesis note** in `notes/_synthesis/<topic>.md` — distill 3+ related notes into a single claim with cited evidence
2. **The connections map** at `notes/_connections.md` — patterns that span multiple categories
3. **The open questions list** at `notes/_open-questions.md` — gaps and unresolved contradictions

### Process (high level)

1. **Read and absorb.** Browse `{shared_dir}/notes/`, especially anything new since the last consolidate. Build a mental map of what's known.
2. **Synthesize.** For any topic with 3+ notes, write or update a synthesis note. State the claim, cite the attempts, name the mechanism, give a confidence + condition. See skill Variant D.1.
3. **Map connections.** Append to `_connections.md` only when a pattern genuinely spans categories (rare — most links live in the synthesis note's "Evidence" section). See skill Variant D.2.
4. **Document contradictions and gaps.** Append to `_open-questions.md` when a claim has counter-evidence or a technique has no experiments yet. See skill Variant D.3.
5. **(Optional) Organize structure.** If the notes folder is disorganized (too many flat files, duplicates, naming issues), use the `organize-files` skill (`{shared_dir}/skills/organize-files/SKILL.md`). Only reorganize within `research/` and `experiments/` — don't touch `raw/`, `_synthesis/`, or `_connections.md`.
6. **(Optional) Extract skills.** If a synthesis reveals a well-validated, reusable technique, promote it to `{shared_dir}/skills/` via `skill-creator/SKILL.md`.

### Step 7: Audit the team's roles, lanes, and postures

Read every agent's role file (`ls {shared_dir}/roles/*.md`) and every active focus note (`ls {shared_dir}/notes/focus/focus-*.md`). Produce a one-paragraph roster summary, either in `{shared_dir}/notes/_connections.md` or as a dated entry in `{shared_dir}/notes/_synthesis/team-roster.md`. The summary should answer:

- **Role coverage** — quote each agent's current role description (one line each) and their generation number. Stable, high-generation, evidence-backed role files are signals of committed specialization. Generation-0 or all-aspirational role files after many evals are signals an agent hasn't found their footing — useful information for the team.
- **Lane coverage** — what techniques/areas are currently in flight (from focus notes)? Are two or more agents on the same lane? Are there obvious unexplored lanes from `_open-questions.md` that nobody is working on?
- **Posture coverage** — synthesizing across roles and focus notes, which functional roles (engineer / researcher / performance engineer / tooling engineer / reviewer / tech writer, or invented variants) are filled, and which are absent? An all-engineer team is a warning sign, especially if scores have plateaued.
- **Stale focus notes** — any focus note whose creator hasn't submitted an eval in the last several heartbeats is probably abandoned. Flag it (or delete it if the creator has clearly moved on).

This roster is read by every agent at planning time. Keeping it accurate is what makes complementary lane/posture choice possible without anyone being assigned a role.

Do **not** edit other agents' role files as part of this audit — those are owned by their authors. The roster is a third-person summary of what the role files already say.

---
The goal is knowledge creation: every consolidation should leave the knowledge base smarter than before.

After consolidating, resume optimizing.
