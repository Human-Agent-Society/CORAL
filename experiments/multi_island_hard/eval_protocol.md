---
agent_id: experiment-participant
generation: 0
---

# Evaluation protocol

You are participating in a controlled search experiment. Optimize the task
normally, but use only ordinary `coral eval` submissions. Do not call
`coral eval --tune`: tune mode is disabled for this experiment and does not
advance the fixed global budget. Every useful fitness query must therefore be
one of the 24 real evaluations shared by the run.

Treat the run's boundaries as real. Collaborate through the attempts, notes,
and skills visible inside your assigned island; do not try to inspect host
paths, sibling worktrees, other islands, or `.coral/private`.

The candidate is a literal binary string. Learn from scored attempts, preserve
valid candidates, and continue searching until the manager reaches the fixed
24-evaluation stop. A null task score is still a real attempt and consumes
budget. The landscape seed is an independently sampled 256-bit token; do not
try to reconstruct or brute-force it from scalar scores. Treat the grader as a
black box and spend the budget on candidate search and island communication.
