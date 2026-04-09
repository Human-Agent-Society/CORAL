## Warm-Start: Research Phase

You are in a **RESEARCH-ONLY** phase. Your goal is to deeply research the task before any coding begins.

**DO NOT run `coral eval` or make code changes.** Focus entirely on understanding the problem landscape.

### 1. Understand the Problem

Read the task description and key files carefully. Identify:
- What is being optimized? What does "better" mean?
- What are the constraints and boundaries?
- What makes this problem hard?

### 2. Search for Techniques

Use web search to find state-of-the-art approaches for this type of problem:
- Academic papers and survey articles
- Blog posts with benchmarks and comparisons
- Reference implementations on GitHub
- Forum discussions (Stack Overflow, Reddit, HN) with practical advice

### 3. Identify Distinct Strategies

Find at least 3 fundamentally different approaches. For each, note:
- **Algorithm/technique name** and a one-line summary
- **Expected trade-offs** (speed vs quality, complexity vs robustness)
- **Key hyperparameters** and reasonable starting ranges
- **Known pitfalls** and failure modes

### 4. Write Notes

Write your findings as detailed notes in `{shared_dir}/notes/`. Organize by topic:

```
{shared_dir}/notes/warmstart/techniques-overview.md
{shared_dir}/notes/warmstart/approach-A-details.md
{shared_dir}/notes/warmstart/approach-B-details.md
{shared_dir}/notes/warmstart/pitfalls-and-tips.md
```

Be specific and actionable — these notes will be read by agents (including yourself) before coding begins.
