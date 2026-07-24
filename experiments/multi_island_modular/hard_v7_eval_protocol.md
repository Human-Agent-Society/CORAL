---
agent_id: experiment-participant-v7
generation: 0
---

# Hard v7 oracle-free threshold protocol

This is a fixed-budget threshold experiment. Use ordinary `coral eval` only;
tune evaluations are disabled. The candidate is a 48-module artifact, with
each module a literal 64-bit string. Only the declared `ACTIVE_MODULE` is
scored. The grader deliberately returns no inactive-module score or assembly
count; the operator computes assembly later from exact active discoveries.

The first action must be the deterministic all-zero baseline for the mapped
module. Do not inspect grader source, hidden paths, or optional skills before
that first real eval. After the baseline, use a compact local loop where
possible. Every loop iteration must still call ordinary `coral eval`, wait for
the returned score, preserve exact modules, and stop before the fixed budget.
The runner reserves exactly one eighth of the global real-evaluation budget
for each agent. When that quota is exhausted, stop submitting; the producer
will reject extra attempts so one fast agent cannot consume another agent's
share.

Use this deterministic initial assignment after stripping a `-from-<island>`
suffix from `.coral_agent_id`:

```
captain-nemo -> 0       captain-ahab -> 1
jack-sparrow -> 2       davy-jones -> 3
long-john-silver -> 4   sinbad-the-sailor -> 5
horatio-hornblower -> 6 jack-aubrey -> 7
```

For an unexpected base id, use the first two bytes of its SHA-256 digest
modulo 8. Treat that value as `base_index`. Probe modules in the deterministic
sequence `base_index, base_index + 8, base_index + 16, ...` modulo 48. Move to
the next module immediately after an exact active result, or after 66 real
attempts on one Smooth module without an exact result. Do not spend the whole
per-agent quota repeatedly verifying the same module. Notes may skip a module
that the current island has already verified, but they must not send every
agent back to module 0. After migration, inspect the arrival note and
`coral log --recent`; carry exact modules with their original bits and record
the source island. Never claim a module merely because untested bits happen to
match a candidate.

The Smooth coordinate/provenance anchor is `48 * (64 + 2) = 3168` real
evaluations. The Rugged public codebook has 4096 distinct 64-bit entries. To
reproduce it without reading grader code, hash the literal UTF-8 string
`coral-hard-v7-codebook:{counter}` with SHA-256, take the first eight bytes as
a big-endian integer masked to 64 bits, skip zero and duplicates, and collect
4096 formatted 64-bit values. The hidden target is one codebook entry under a
private per-seed permutation. A wrong nonzero Rugged code scores 0.10, zero
scores 0.08, and an exact target scores 1.0. Only an exact active response is
evidence of a tested building block.

Before every submission, verify that `CANDIDATE` has exactly 48 binary
strings of length 64 and `ACTIVE_MODULE` is in `[0, 48)`. A malformed
submission receives score 0, consumes a real attempt, and supplies no
evidence. Do not replace the literal tuple with a comprehension, repetition,
function call, or computed expression. Preserve every
exact module while probing another one; do not reset it to zero in a later
candidate.

This protocol is an allocation/transfer mechanism study. A positive result is
not evidence of semantic collaboration or institution-building without the
separate communication ablations specified in `research_design_v7.md`.
