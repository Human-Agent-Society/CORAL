---
agent_id: scaling-experiment-participant
generation: 0
---

# Scaling experiment protocol

## HARD BOUNDARY (must follow)

Do not probe for hidden data or host checkouts. In particular, never run
`find /`, `find ~`, `find /home`, `ls /home`, `ls /jfs`, or any recursive
search outside the current worktree and the public `.opencode/`/`.coral/`
state. Never search for `frozen_problem.py`, `taskdata`, or
`submission_tests.py` by name, even with a relative `find .` or
`find .coral` command. Never run `ls`, `cat`, `rg`, Python, or another tool against
`.coral/private/` (even to check whether it is empty). The simulator and
answer data are intentionally unavailable. A permission error is a boundary,
not a reason to retry with a different path. If the runtime rejects a tool call
before execution, no probe occurred and the cell remains valid; do not retry it.
Any forbidden probe that actually executes invalidates this experimental cell.
Continue by using only the task files, public grader source, public
attempts/feedback, and your own worktree.

Do not use `find` or OpenCode's glob tool anywhere in this experiment, even
inside your own worktree. Use explicit relative paths only. Never inspect the
run root or the parent `agents/` directory. After a migration, `.opencode/`
already points at your destination island: use `coral log`, `coral show`,
`coral notes`, or a known `.opencode/attempts/<hash>.json` path. Never locate
attempts, notes, or teammates by recursively searching the run directory.

You are participating in a controlled multi-agent scaling experiment. Work
directly on the assigned optimization task and submit ordinary real
evaluations with `coral eval`. Do not use `coral eval --tune`.

Each agent has a small, equal real-evaluation quota. Submit a serious first
candidate promptly, read its grader feedback, and use the remaining quota to
make the strongest correction or improvement you can. Do not spend the whole
run only researching or inspecting infrastructure. Never wait for a human.

Use the attempts, notes, skills, and same-island worktrees that CORAL exposes.
Do not inspect host paths, sibling runs, other islands, or `.coral/private`.
Do not spawn nested agents: the experimental population is the set of agents
started by CORAL, and nested workers would make the population size ambiguous.
Never invoke OpenCode's `task` tool or an explore/general subagent.

For Kernel Builder, only optimize `kernel_builder.py`; hidden simulator data is
unavailable by design. For Pack the Polyominoes, keep `solution.cpp`
self-contained and C++17-compatible.
