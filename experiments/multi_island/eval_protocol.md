---
agent_id: experiment-participant
generation: 0
---

# Evaluation protocol

You are participating in a controlled search experiment. Optimize the task
normally, but use only ordinary `coral eval` submissions. Do not call
`coral eval --tune`: tune mode is disabled for this experiment and does not
advance the fixed global budget. Every useful fitness query must therefore be
one of the 16 real evaluations shared by the run.

Treat the run's boundaries as real. Collaborate through the attempts, notes,
and skills visible inside your assigned island; do not try to inspect host
paths, sibling worktrees, other islands, or `.coral/private`.

For Kernel Builder, the grader constructs your instruction stream in a separate
candidate sandbox and only then invokes the private simulator. The simulator
module is intentionally unavailable while your code is being built; importing
or copying hidden grader data is a protocol violation and produces no useful
result.
