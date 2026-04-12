# Research Note Template

Use this when writing notes to `notes/research/`.

```markdown
---
title: "Research: [Topic]"
creator: {agent_id}
created: [ISO timestamp]
tags: [research]
---

# [Topic]

## Problem
[What we're solving and how it's evaluated]

## Approaches Considered

| Approach | Evidence | Complexity | Expected Performance |
|----------|----------|------------|---------------------|
| [A]      | strong/moderate/weak | low/medium/high | estimated range |
| [B]      | strong/moderate/weak | low/medium/high | estimated range |

### Approach A: [Name]
- **Description**: ...
- **Evidence**: [paper/benchmark] — see [raw/source.md](../raw/source.md)
- **Pros**: ...
- **Cons**: ...

### Approach B: [Name]
...

## Selected Approach
[Which and why]

## Experiment Results
(Updated by reflect heartbeat after evals)
- Eval N: scored X — [what worked, what didn't]

## References
- [Title](../raw/source-name.md) — one-line summary
```

**Tips:**
- Be specific: "Use RDKit's Crippen module for logP" beats "use a chemistry library"
- Include numbers: "Method X achieved 0.85 AUC on benchmark Y" beats "works well"
- Flag uncertainties: if you're not sure a method applies, say so
