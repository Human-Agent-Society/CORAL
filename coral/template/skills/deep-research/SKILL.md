---
name: deep-research
description: "Use this skill BEFORE starting implementation on any non-trivial task. Conducts deep research — web searches, literature review, existing solution analysis, and approach exploration — then produces a structured research summary. Prevents wasted iterations by grounding your approach in what's already known."
creator: system
created: 2025-04-10T00:00:00Z
---

# Deep Research Before Implementation

Conduct thorough research and literature review before writing any code. Understand the problem space, survey existing solutions, and design an informed approach — then implement.

<HARD-GATE>
Do NOT start implementing until you have completed the research phase and written a research summary to shared notes. This applies to every non-trivial task. "Non-trivial" means anything where the right approach isn't immediately obvious or where multiple valid strategies exist.
</HARD-GATE>

## When to Use This Skill

- Starting a new optimization task or problem you haven't solved before
- The problem involves domain-specific knowledge (biology, chemistry, physics, math, etc.)
- Multiple valid approaches exist and you need to pick the best one
- Previous attempts have plateaued and you need fresh ideas
- The evaluation metric or objective function is complex or unfamiliar

## When to Skip

- You've already researched this exact problem in a prior attempt
- The task is a direct iteration on a working approach (parameter tuning, minor fixes)
- A shared note already covers the research you'd do

## Research Process

You MUST complete these steps in order:

### 1. Understand the Problem

Before searching externally, make sure you deeply understand what you're optimizing for.

- Read the task description, grader code, and evaluation criteria carefully
- Identify the objective function — what exactly is being measured?
- Identify constraints — what are the hard limits?
- Check existing attempts (`coral log`) — what has been tried? What scores did they get?
- Check shared notes (`coral notes`) — has anyone already researched this?

### 2. Survey the Literature

Use web search to find relevant research, papers, and existing solutions.

**Search strategy — cast a wide net, then focus:**

1. **Broad survey** — search for the problem class:
   - `"[problem domain] state of the art methods"`
   - `"[problem domain] best algorithms"`
   - `"[problem domain] survey paper"`
   - `"[problem domain] benchmark comparison"`

2. **Specific techniques** — once you identify promising approaches:
   - `"[technique name] implementation details"`
   - `"[technique name] python library"`
   - `"[technique name] vs [alternative] comparison"`
   - `"[technique name] hyperparameter tuning"`

3. **Domain knowledge** — understand the underlying science:
   - `"[domain concept] explained"`
   - `"[domain concept] for machine learning"`
   - `"[domain property] optimization"`

4. **Practical implementations** — find code and libraries:
   - `"[problem] python implementation github"`
   - `"[problem] open source solution"`
   - `"[library name] tutorial [problem type]"`

**Reading papers and articles:**
- Focus on methodology sections — how did they solve it?
- Note the datasets and benchmarks — are they comparable to your task?
- Check results tables — what performance did different methods achieve?
- Look at ablation studies — which components matter most?

### 3. Analyze Existing Solutions

If there are existing attempts or shared skills:

- What approaches were used?
- Where did they succeed and fail?
- What patterns emerge from high-scoring vs low-scoring attempts?
- Are there common failure modes?

### 4. Explore Approaches

Based on your research, identify 2-4 candidate approaches:

For each approach, document:
- **What it is** — one-sentence description
- **Why it might work** — connection to the problem structure
- **Known limitations** — when it fails or scales poorly
- **Estimated complexity** — how hard is it to implement?
- **Evidence** — papers, benchmarks, or reasoning supporting it

### 5. Select and Plan

Pick your approach based on:
- Strength of evidence (proven methods > novel ideas for first attempts)
- Implementation feasibility (can you build it with available tools?)
- Expected performance (what scores have similar approaches achieved?)
- Iteration potential (can you incrementally improve it?)

### 6. Write Research Summary

Write a structured research note and save it to shared notes so other agents benefit.

**Use this format:**

```markdown
---
title: "Research: [Problem/Topic Name]"
creator: {agent_id}
created: [ISO timestamp]
tags: [research, domain-tag, approach-tag]
---

# Research: [Problem/Topic Name]

## Problem Understanding
[What we're optimizing, key constraints, evaluation criteria]

## Literature Review
[Key findings from papers, articles, existing solutions]
[Include specific references with URLs when available]

## Approaches Considered
### Approach 1: [Name]
- Description: ...
- Evidence: ...
- Pros: ...
- Cons: ...

### Approach 2: [Name]
...

## Selected Approach
[Which approach and why]

## Implementation Plan
[High-level steps for the chosen approach]

## Key References
- [Title](URL) — one-line summary
- ...
```

Save to: `{shared_dir}/notes/research-[topic].md`

## Key Principles

- **Evidence over intuition** — prefer approaches with empirical support
- **Breadth before depth** — survey widely before committing to one approach
- **Document everything** — your research benefits all agents, not just you
- **Time-box the research** — deep research is valuable, but don't spend forever. 3-5 searches on the broad topic, 2-3 on specific techniques, then decide.
- **Build on what exists** — always check notes and past attempts first
- **Cite your sources** — include URLs so others can verify and dig deeper

## Common Pitfalls

1. **Skipping research because the task "looks simple"** — many problems have non-obvious optimal solutions. A 10-minute search can save hours of wrong-direction implementation.

2. **Researching without focus** — start with the objective function. Everything you read should connect back to "how does this help me score higher?"

3. **Implementing the first thing you find** — survey at least 2-3 approaches before committing. The first result is rarely the best.

4. **Not checking shared notes** — another agent may have already done this research. Don't duplicate effort.

5. **Over-researching** — if you've found 2-3 strong candidates with evidence, stop researching and start building. You can always research more after seeing initial results.
