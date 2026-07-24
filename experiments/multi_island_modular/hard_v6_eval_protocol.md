---
agent_id: experiment-participant-v6
generation: 0
---

# Hard v6 verified-assembly protocol

This is a fixed-budget threshold experiment. Use ordinary `coral eval` only;
tune evaluations are disabled. The candidate is a 48-module artifact: each
module is a literal 32-bit string and only the declared `ACTIVE_MODULE` gets
local search feedback.

**Startup rule:** your first action must be the deterministic all-zero baseline
submission for your mapped module. Do not inspect the grader source, hidden
paths, or optional skills before that first real eval. Startup work that does
not produce a submitted baseline is not useful experimental progress.

Every feedback JSON also contains `artifact_exact_count`. This is an actual
grader reward for exact modules carried by the complete candidate, not an
operator-only diagnostic. It does not reveal which inactive modules are
exact. Preserve every exact module you have tested, record its module index,
bits, attempt hash, score, and discovery island in a note, and carry those
modules when changing `ACTIVE_MODULE`.

Use a deterministic first assignment to avoid startup collisions. Read
`.coral_agent_id`, strip a `-from-<island>` suffix, and use this mapping for
the standard eight-agent roster:

```
captain-nemo -> 0       captain-ahab -> 1
jack-sparrow -> 2       davy-jones -> 3
long-john-silver -> 4   sinbad-the-sailor -> 5
horatio-hornblower -> 6 jack-aubrey -> 7
```

For an unexpected base id, use the first two bytes of its SHA-256 digest
modulo 48. After the first claim, allocate modules using same-island notes,
verified attempts, and (after migration) the arrival agent's carried
candidate. Do not reset an exact module to zero while probing another one.

The smooth coordinate/provenance anchor is `48 * (32 + 2) = 1632` real
evaluations for a complete artifact. The rugged codebook has 2048 entries.
To reproduce it without reading grader code, hash the literal UTF-8 string
`coral-hard-v6-codebook:{counter}` with SHA-256, take the first four bytes as
a big-endian integer masked to 32 bits, skip zero and duplicates, and collect
2048 formatted 32-bit values. Use distinct agent-specific offsets and never
repeat a failed `(module, code)` pair. A rugged wrong nonzero code scores
0.10, zero scores 0.08, and exact scores 1.0; only exact feedback is evidence
of a target.

After every migration, first inspect the arrival note and `coral log --recent`.
If a carried candidate contains an exact module, copy that module into your
own artifact and submit it on the destination island so the transfer is
observable. Do not claim a module merely because its bits happen to appear in
a candidate without a provenance-backed exact attempt.

It is allowed and encouraged to automate a sequence of ordinary `coral eval`
calls with a local script after the first probe. Every call must still consume
one real budget unit, wait for its score, preserve all known modules, and stop
before the declared budget. Never call the grader directly or use tune mode.

Before each submission, check that `CANDIDATE` has exactly 48 binary strings of
length 32 and that `ACTIVE_MODULE` is in `[0, 48)`; a malformed submission
consumes a real attempt and provides no evidence.
