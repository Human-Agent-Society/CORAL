---
agent_id: experiment-participant-threshold-v2
generation: 0
---

# Replicated boundary/diversity threshold protocol

This is the free-allocation companion to the certified component-transfer
study. Optimize the literal 128-bit `CANDIDATE` using ordinary `coral eval`
only. Tune is disabled. The runner reserves exactly one eighth of the global
real-evaluation budget for each of eight agents.

For the first real evaluation, create a topology-invariant diverse start from
your base agent id (strip any `-from-<island>` suffix): compute SHA-256 of
`coral-threshold-v2:{base_id}`, take the first 128 digest bits, and submit that
literal string. Do not submit the common
all-zero seed first. This gives the same eight initial lineages in every
condition without assigning agents to coordinates or solution regions.

After that first query, search normally. Use one-bit ascent, structured
mutations, restarts, copying, or coordination as you judge useful from the
feedback visible to you. Collaborate only through the attempts, notes, skills,
and sibling worktrees visible in the current island. The protocol deliberately
does not tell you to preserve diversity or copy a champion: whether visibility
causes convergence is one of the measured mechanisms. After migration, treat
the arrival as another candidate to evaluate rather than assuming its recent
score transfers unchanged.

The budget is intentionally large. After the required first submission, you
may use a compact local shell loop for mechanical search: each iteration must
still write one literal `CANDIDATE`, call ordinary `coral eval`, wait for its
feedback, and choose the next candidate from information visible in your
island. Do not call the grader directly or batch uncounted fitness queries.

The Smooth task has K=0 and one one-bit local optimum. The Rugged task has
K=12 and many basins. Both use eight paired held-out 256-bit seeds and a budget
ladder large enough to move beyond the old 16/24-query smoke tests. Sandbox
networking is restricted to the model API. Do not inspect private paths, infer the seed, or treat
the operator's approximate greedy reference as a known optimum.
