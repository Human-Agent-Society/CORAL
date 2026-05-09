---
name: deep-research
description: "Research the problem domain before coding. Web search for techniques, save raw sources, write structured findings, update the index."
---

# Deep Research

Research the problem thoroughly before writing code. Understand what's known, what's been tried, and what approaches exist.

## When to Use

- Starting a new task or problem
- Stuck after multiple evals without improvement
- Pivoting to a fundamentally different approach
- The problem involves domain-specific knowledge you're unfamiliar with

## Notes Directory Structure

```
notes/
├── index.md          ← table of contents for research/ and experiments/
├── raw/              ← saved web pages, paper excerpts (immutable, never edit)
├── research/         ← your synthesized findings (link back to raw/)
└── experiments/      ← eval reflections and results (written by reflect heartbeat)
```

## Process

### 1. Understand the Problem

Read the task description and key files. Identify what's being optimized, what the constraints are, and what makes it hard. Check `coral log` and `{shared_dir}/notes/` for prior work.

### 2. Search — Cast a Wide Net, Then Focus

**Broad survey** — search for the problem class:
- `"[problem domain] state of the art methods"`
- `"[problem domain] survey paper"`
- `"[problem domain] benchmark comparison"`

**Specific techniques** — once you identify promising approaches:
- `"[technique name] vs [alternative] comparison"`
- `"[technique name] implementation details"`
- `"[technique name] python library"`

**Practical implementations** — find code and libraries:
- `"[problem] python implementation github"`
- `"[problem] open source solution"`

Do 3-5 focused searches. When reading papers and articles, focus on methodology and results tables — how did they solve it, and what performance did they achieve?

### 3. Save Raw Sources

For every useful source, save the raw content so it can be verified later:

```
{shared_dir}/notes/raw/source-name.md
```

Use `WebFetch` to get the full page, then write it to `notes/raw/`. These are immutable — never edit raw sources, only reference them from research notes.

When the source is **not a plain web article** (paper PDF, GitHub repo, video, conference talk, internal docs, chat log…), see [`references/source-types.md`](references/source-types.md) for capture procedure, what to extract, and the right frontmatter fields per type. Generic `WebFetch` only handles ~half of real research inputs cleanly.

When `WebFetch` fails, sources contradict, search returns nothing useful, or you find an existing-but-stale note covering your topic, see [`references/failure-modes.md`](references/failure-modes.md) for diagnosis and recovery procedures.

### 4. Compare Approaches

Identify 2-4 candidate approaches. For each, document:
- **What it is** — one-sentence description
- **Why it might work** — connection to the problem structure
- **Known limitations** — when it fails or scales poorly
- **Estimated complexity** — how hard is it to implement?
- **Evidence** — papers, benchmarks, or reasoning supporting it
- **Raw source** — link to `notes/raw/` entry

Pick your approach based on strength of evidence, implementation feasibility, and iteration potential. Proven methods beat novel ideas for first attempts.

### 5. Write Research Notes

Summarize your findings in `{shared_dir}/notes/research/`. For each technique or approach, note:
- What it is and how it works
- Expected trade-offs
- Key parameters and pitfalls
- Links back to raw sources (e.g., `see [raw/paper-name.md](../raw/paper-name.md)`)

Keep notes specific and actionable. "X might work" is weak. "X reduces Y by 30% when Z > 10 (see raw/paper-name.md)" is useful. See `references/research-note-template.md` for a structured format.

After writing or substantially updating a note, **optionally** spawn the Synthesis Reviewer subagent to verify grounding before adding the note to the index. The reviewer reads the note alongside its linked raw sources and returns a per-claim verdict (`grounded` / `partially-grounded` / `inferred` / `contradicted` / `unverifiable`) — useful because the author of a synthesis cannot objectively grade its own grounding. See [`agents/synthesis-reviewer.md`](agents/synthesis-reviewer.md) for inputs and output schema. Spawn it especially when:

- The note synthesizes 3+ raw sources and you want confidence the merge is faithful.
- A subsequent agent is auditing older notes during organize-files.
- The note's `confidence` field will be set to `high` and you want to back that up.

### 6. Update Index

Create or update `{shared_dir}/notes/index.md`. The index only lists research notes and experiment notes — not raw sources:

```markdown
# Notes Index

## Research
- [technique-a](research/technique-a.md) — one-line summary
- [technique-b](research/technique-b.md) — one-line summary

## Experiments
- (none yet)

## Open Questions
- What hasn't been tried?
```

Raw sources are accessed by following links inside research notes, not through the index.

After writing a new note, run the link resolver so existing notes pick up cross-references to it:

```bash
python .coral/public/skills/organize-files/scripts/resolve_links.py {shared_dir}/notes/ --new <new-slug>
```

The `--new` flag scans every existing note for plain-text mentions of the new title and wraps them as `[[wikilinks]]` — without this, manual cross-referencing decays as the notes directory grows.

## Maintaining Notes Across Sessions

Research notes evolve as new raw sources arrive and old ones decay. A few rules keep the synthesis honest as the corpus grows.

### Multi-source synthesis — re-write from ALL contributors

When 2+ raw sources inform the same topic, the research note must draw from **every linked source**, not just the most recent one. On a follow-up research pass that finds a new source covering an existing topic:

- **Update the existing note**, don't fork. `research/topic-v2.md` is wrong — there should be one note per topic.
- Re-read each linked raw source and rewrite the synthesis from the full set, not just the new one.
- Append the new source to the `## References` section.

If you only re-synthesize from the new source, you silently drop evidence from the old ones — which means re-research can quietly *reduce* the note's grounding instead of strengthening it.

### Stale or invalid sources — freeze, don't overwrite

When a raw source becomes invalid (link rot, retraction, supersession by a newer paper):

- **Don't rewrite the note immediately.** Add `needs-reverification: [list of claims]` to the frontmatter and move on.
- Only rewrite once you can confirm which claims survive on the remaining sources.
- If the note loses *all* its supporting sources, set `superseded: true` rather than deleting the file — it preserves the audit trail for future agents who might rediscover the topic.

### Partial re-verification preserves combined work

If a note synthesizes A + B + C and you only have time to re-verify against B, **leave the note body alone**. A partial rewrite that keeps only B's perspective drops the synthesis from A and C. Either re-verify against the full source set or note the partial check in the frontmatter (`partially-verified: [B]`) without touching the body.

## Principles

- **Save raw sources** — summaries can be wrong, raw sources are ground truth
- **Breadth before depth** — survey 3+ approaches before committing to one
- **Compare before committing** — always evaluate 2-4 candidates, don't latch onto the first result
- **Build on what exists** — check notes and past attempts first
- **Cite your sources** — link research notes back to `notes/raw/`
- **Don't over-research** — 3-5 searches, write notes, start coding
