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

## Principles

- **Save raw sources** — summaries can be wrong, raw sources are ground truth
- **Breadth before depth** — survey 3+ approaches before committing to one
- **Compare before committing** — always evaluate 2-4 candidates, don't latch onto the first result
- **Build on what exists** — check notes and past attempts first
- **Cite your sources** — link research notes back to `notes/raw/`
- **Don't over-research** — 3-5 searches, write notes, start coding
