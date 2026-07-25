---
agent_id: experiment-participant-v8
generation: 0
---

# Certified-composition v8 protocol

This is a fixed-budget search-and-transfer study. Use ordinary `coral eval`
only. Every accepted attempt must keep these three assignments literal:

```python
CANDIDATE = ("...32 bits...", ... 32 entries total ...)
ACTIVE_MODULE = 0
CERTIFICATES = (None, ... 32 entries total ...)
```

An exact active evaluation returns a `v8c-...` certificate. It is valid only
for that mode, hidden seed, module index, and exact bits. Put the token at the
same index in `CERTIFICATES` on the next submission. Never attach a token to
changed bits. Invalid syntax or a mismatched certificate scores zero and still
uses quota. `verified_count` reports only certificates already supplied plus a
new certificate issued by the current exact evaluation; it is not an oracle
over uncertified inactive bits.

## Deterministic positive-control lanes

Strip a `-from-<island>` suffix from `.coral_agent_id` and use this base index:

```text
captain-nemo -> 0       captain-ahab -> 1
jack-sparrow -> 2       davy-jones -> 3
long-john-silver -> 4   sinbad-the-sailor -> 5
horatio-hornblower -> 6 jack-aubrey -> 7
```

For an unexpected id, use the first two bytes of its SHA-256 digest modulo 8.
Your owned lane is `base_index, base_index + 8, base_index + 16,
base_index + 24`. Work in that order and do not duplicate another agent's
lane. This balanced assignment is deliberate: it is a positive control for
whether migration can carry complementary verified expertise, not evidence
that free-form societies will spontaneously specialize the same way.

Before every evaluation, merge every certificate-backed module visible in
your current island's notes, recent log, and sibling worktrees. After each
exact result, record module index, exact bits, certificate, commit, and your
island in a compact shared note. After migration, merge the migrant's carried
certificates with destination-local certificates and submit a consolidation
candidate promptly. The primary metric counts the best certificate-backed
candidate actually submitted; an operator-side union does not count.

## Smooth search

Start an owned module from zero and record its active score. Probe each of its
32 coordinates once, retaining a flip only when `active_score` improves. The
evaluated probe itself can be the new incumbent. After all coordinates, submit
the reconstructed incumbent once if the last evaluated probe was not exact.
This costs at most 34 real evaluations per certified module. Read
`active_score` from feedback; the aggregate score also contains a small
certificate-preservation term used for migration ranking.

## Rugged search

Each module is four contiguous 8-bit groups. Every group has a private random
256-entry fitness table, one unique score-1 value, a strong score-0.90 decoy,
and many local maxima. Coordinate ascent is not a target-recovery oracle.

To solve a module deterministically, hold three groups fixed and enumerate all
256 literal values of the remaining group, recording the best active score.
Keep that best value fixed, then enumerate the next group. After four groups,
submit their four best values together to obtain the module certificate. This
costs at most `4 * 256 + 1 = 1025` evaluations. Use a compact local loop, but
every iteration must still write literal assignments, call ordinary
`coral eval`, wait for its feedback, and respect your per-agent quota.

Once all four owned modules are exhausted or certified, stop new discovery and
consolidate. Do not inspect grader-private paths, reconstruct the 256-bit seed,
use tune, or claim uncertified bits as knowledge.
