---
agent_id: experiment-participant-v4
generation: 0
---

# Hard v4 modular evaluation protocol

This is a fixed-budget threshold experiment. Use ordinary `coral eval` only;
tune evaluations are disabled. Prefer this literal representation:

```python
CANDIDATE = (
    "000000000000000000000000",
    # exactly 24 module literals in total
)
ACTIVE_MODULE = 0
```

There are 24 contiguous 24-bit modules. Each real evaluation scores only the
declared `ACTIVE_MODULE`. A score of exactly `1.0` is the only evidence that
the selected module is an exact tested building block. Preserve exact tested
modules when probing a different module, and record the candidate, module,
score, and provenance in a note. Do not claim an untested module merely
because its bits happen to occur in a candidate.

The smooth task returns a Hamming-match score. The conservative coordinate
baseline is 24 modules times 25 probes, or 600 evaluations. The rugged task
returns `0.78` for the all-zero trap, `0.43` for every non-target code, and
`1.0` for the hidden target. Its 512-entry codebook is public and can be
enumerated; only the per-seed permutation and target seed are private.

Before searching, derive a stable enumeration offset from your own agent ID
and use a different offset from nearby agents when possible. Record the
offset and claimed `(module, code)` pairs in notes so isolated communities do
not spend the same budget. A migration arrival is evidence to verify and
preserve, not a reason to discard local provenance.

Before every submission, run a literal check: the tuple must have exactly 24
strings, each length 24, containing only `0` and `1`; `ACTIVE_MODULE` must be
an integer in `[0, 24)`. A malformed candidate consumes a real attempt and
cannot provide evidence. Continue until the manager reaches the declared
real-evaluation stop.
