# Research Note Template

Use this template when writing research summaries to shared notes.

## Minimal Template (for focused problems)

```markdown
---
title: "Research: [Topic]"
creator: {agent_id}
created: [ISO timestamp]
tags: [research]
---

# Research: [Topic]

## Problem
[What we're solving and how it's evaluated]

## Key Findings
- [Finding 1 with source]
- [Finding 2 with source]

## Recommended Approach
[What to do and why, based on the findings]

## References
- [Source](URL)
```

## Full Template (for complex/domain-heavy problems)

```markdown
---
title: "Research: [Topic]"
creator: {agent_id}
created: [ISO timestamp]
tags: [research, domain-tag, approach-tag]
---

# Research: [Topic]

## Problem Understanding
- **Objective**: [What exactly is being optimized/measured]
- **Constraints**: [Hard limits, requirements]
- **Evaluation**: [How the grader scores solutions]
- **Baseline**: [Current best score and approach, if known]

## Literature Review

### [Subtopic 1]
[Key findings, methods described in the literature]
- Source: [Title](URL)

### [Subtopic 2]
[Key findings, methods described in the literature]
- Source: [Title](URL)

## Approaches Considered

| Approach | Evidence | Complexity | Expected Performance |
|----------|----------|------------|---------------------|
| [A]      | [strong/moderate/weak] | [low/medium/high] | [estimated range] |
| [B]      | [strong/moderate/weak] | [low/medium/high] | [estimated range] |
| [C]      | [strong/moderate/weak] | [low/medium/high] | [estimated range] |

### Approach A: [Name]
- **Description**: ...
- **Evidence**: [paper/benchmark/reasoning]
- **Pros**: ...
- **Cons**: ...
- **Implementation notes**: [libraries, key parameters, gotchas]

### Approach B: [Name]
...

## Selected Approach
[Which approach, why, and what evidence supports the choice]

## Implementation Plan
1. [Step 1]
2. [Step 2]
3. ...

## Open Questions
- [Things to figure out during implementation]

## Key References
- [Title](URL) — [one-line summary of relevance]
- [Title](URL) — [one-line summary of relevance]
```

## Tips

- **Be specific**: "Use RDKit's Crippen module for logP calculation" beats "use a chemistry library"
- **Include numbers**: "Method X achieved 0.85 AUC on benchmark Y" beats "Method X works well"
- **Note versions**: "Tested with sklearn 1.3, API changed in 1.4" saves debugging time
- **Flag uncertainties**: If you're not sure a method applies to your exact problem, say so
