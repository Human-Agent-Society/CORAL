# Research Note Template

Use this when writing notes to `notes/research/`. A research note is a **synthesis, not a bibliography** — it leads with what you concluded and spends citations to back it, rather than listing what each source said and leaving the reader to synthesize.

```markdown
---
title: "Research: [Topic]"
creator: {agent_id}
created: [ISO timestamp]
confidence: low        # low | medium | high — high requires passing synthesis review
tags: [research]
references:
  - raw/source-a.md
  - raw/source-b.md
---

# [Topic]

## Bottom line
[The one-paragraph synthetic claim this note exists to make — what should the team
*do* or *believe* after reading it. Lead with the conclusion, not the setup.]

## Problem
[What we're solving and how it's evaluated — one or two sentences.]

## What the evidence says
[Prose, one claim per paragraph, each opening on YOUR synthetic point and then
spending citations to support it. "The effect is real but modest, clustering at
35–40% (see [raw/chen-2019.md](../raw/chen-2019.md); [raw/park-2020.md](../raw/park-2020.md))"
is a finding. "Chen reported 40%; Park reported 35%" is two index cards — synthesize them.]

## Approaches — head to head
[A compact table is the right structure *here* (and only here). Everything else is prose.]

| Approach | Evidence (strong/moderate/weak) | Complexity | Expected performance | Source |
|----------|--------------------------------|------------|----------------------|--------|
| [A]      | strong  | low    | estimated range | [raw/a.md](../raw/a.md) |
| [B]      | weak    | high   | estimated range | [raw/b.md](../raw/b.md) |

## Selected approach
[Which, and *why* — tie it to the evidence above, not to a gut call.]

## Experiment Results
(Updated by reflect heartbeat after evals)
- Eval N: scored X — [what worked, what didn't]

## References
- [Title](../raw/source-name.md) — one-line summary of what it contributes
```

**The synthesis diagnostic** (from the literature-review discipline): read only the first sentence of each paragraph in sequence. If they form your argument, you've written a synthesis. If they form a list of source names, you've written an annotated bibliography in paragraph costume — rewrite it.

**The insight-vs-context filter:** before you record a finding, ask *"would a senior member of the field (5+ years) find this surprising or decision-relevant?"* If yes, it's an insight worth a note. If no, it's context — fold it into a sentence, don't give it its own note. This keeps the base from bloating with things everyone already knows.

**Tips:**
- Be specific: "Use RDKit's Crippen module for logP" beats "use a chemistry library"
- Include numbers *with a source*: "Method X achieved 0.85 AUC on benchmark Y (see [raw/x.md](../raw/x.md))" beats "works well"
- Flag uncertainties: if you're not sure a method applies, say so — and keep `confidence: low` until you've verified
