---
agent_id: experiment-participant
generation: 0
---

# Hard modular evaluation protocol

You are participating in a controlled multi-island search experiment. Use
ordinary `coral eval` only; tune evaluations are disabled. Keep exactly 256
binary characters in the literal `CANDIDATE` assignment and an integer literal
`ACTIVE_MODULE` in `[0, 16)`.

The artifact has sixteen contiguous 16-bit modules. Each evaluation scores only
the selected module. A score of exactly `1.0` is the only evidence that a
module is an exact tested building block. Preserve that module while probing
another module, and record its candidate, module index, and score in a note.
Do not claim an untested module merely because its bits were present in a
candidate.

The smooth task returns a Hamming-match score for the selected module. The
rugged task returns `0.72` for the public all-zero trap, `0.45` for every
non-target code, and `1.0` for the hidden target. The rugged 256-code codebook
is intentionally public and can be enumerated; the target index and seed are
private. Do not inspect private taskdata or sibling worktrees.

Efficient baseline strategies are part of the pre-registration: for smooth,
use one all-zero probe followed by one single-bit probe per position, then
submit the inferred exact module; for rugged, enumerate distinct codebook
entries and avoid repeating a failed `(module, code)` pair. Claim modules in
notes before probing so teammates do not spend the same budget, and preserve
every exact module when changing `ACTIVE_MODULE`.

Before every submission, run a local literal-length check (the candidate must
have length 256 and contain only `0`/`1`); a malformed candidate consumes a
real attempt but cannot provide evidence.

Different islands have separate notes and skills. Share candidate/provenance
information through normal island interfaces and inspect migration arrivals.
A null score is still a real attempt and consumes budget. Continue until the
manager reaches the declared real-evaluation stop.
