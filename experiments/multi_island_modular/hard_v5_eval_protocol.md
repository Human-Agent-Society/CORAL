---
agent_id: experiment-participant-v5
generation: 0
---

# Hard v5 modular threshold protocol

This is a fixed-budget threshold experiment. Use ordinary `coral eval` only;
tune evaluations are disabled. Prefer this literal representation:

```python
CANDIDATE = (
    "00000000000000000000000000000000",
    # exactly 32 module literals in total
)
ACTIVE_MODULE = 0
```

There are 32 contiguous 32-bit modules. Each real evaluation scores only the
declared `ACTIVE_MODULE`. A score of exactly `1.0` is the only evidence that
the selected module is an exact tested building block. Preserve exact tested
modules when probing a different module, and record the candidate, module,
score, and provenance in a note. Do not claim an untested module merely
because its bits happen to occur in a candidate.

To keep the threshold pilot from measuring simultaneous startup collisions,
use a deterministic first assignment. Read your own `.coral_agent_id`, strip
the `-from-<island>` suffix when present, hash the remaining base id with
SHA-256, and set the first `ACTIVE_MODULE` to the integer represented by the
first two digest bytes modulo 32. Do not default every agent to module 0.
After the first claim is recorded, agents may reallocate modules using their
island's notes and verified attempts. This fixed initial allocation is part of
the protocol, not a post-hoc rescue.

The smooth task returns deterministic Hamming-match feedback. A coordinate
probe needs 32 modules times 33 probes (one all-zero plus 32 one-bit probes),
and a further exact submission is needed per module for provenance. Thus the
full-artifact coordinate anchor is 32 * 34 = 1,088 real evaluations.

The rugged task returns `0.38` for the all-zero decoy, `0.42` for every
non-target nonzero code, and `1.0` for the hidden target. Its public codebook
has 1,024 distinct 32-bit entries and can be enumerated; only the per-seed
permutation and target seed are private. The decoy is deliberately below a
wrong nonzero code so score-based migration does not reward abandoning the
enumeration. Record a stable agent-specific enumeration offset and avoid
repeating a failed `(module, code)` pair.

Before every submission, run a literal check: the tuple must have exactly 32
strings, each length 32, containing only `0` and `1`; `ACTIVE_MODULE` must be
an integer in `[0, 32)`. A malformed candidate consumes a real attempt and
cannot provide evidence. Continue until the manager reaches the declared
real-evaluation stop.
