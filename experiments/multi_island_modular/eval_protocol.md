---
agent_id: experiment-participant
generation: 0
---

# Modular evaluation protocol

You are participating in a controlled multi-island search experiment.  Use
only ordinary `coral eval` submissions.  Tune evaluations are disabled and do
not advance the fixed real budget.  Every accepted candidate must keep exactly
128 binary characters in the literal `CANDIDATE` assignment and an integer
literal `ACTIVE_MODULE` in `[0, 16)`.

The candidate consists of sixteen contiguous 8-bit modules.  Each evaluation
tests only `ACTIVE_MODULE` and returns only that module's score.  Treat a module
whose score reaches 1.0 as a tested building block: preserve it while selecting
and searching other modules, and record the candidate, score, and module index
in a typed experiment note.  Do not overwrite a higher-scoring module without a
measured reason.  The target codes and task seed are hidden; do not inspect
host paths, sibling worktrees, or `.coral/private`, and do not attempt seed
recovery.

Different islands intentionally have separate notes and skills.  Share useful
candidate/provenance information through the normal island interfaces.  A
migrant may carry its tested candidate and evaluation history, so inspect the
arrival information before restarting a search.  A null score is still a real
attempt and consumes budget.  Continue until the manager reaches the declared
real-evaluation stop.
