# Preregistered v6 difficulty-construct audit

## Purpose

This audit tests whether the axes called “Smooth size” and “Rugged epistasis”
in the v6 phase map actually span materially different search regimes. It is
frozen before `threshold_v6_phase_map_raw.json` exists, reads no topology
outcome, and cannot alter or rescue the phase-map decision rule.

## Frozen diagnostics

The audit uses the same 24 held-out landscape seeds as the v6 phase map. For
each adjacent-NK `K = 8, 16, 32, 64, 128`, it draws 256 deterministic random
points per block and pairs each point with one uniformly selected one-bit
neighbour. It reports:

- one-bit score autocorrelation;
- mean absolute one-bit score change in within-instance random-SD units;
- one-bit score-change SD in within-instance random-SD units; and
- the exact affected-component fraction `(K + 1) / 512`.

The RNG namespace is separate from both the phase-map search policy and its
random-reference stream. The audit does not simulate agents, visibility,
migration, or any topology.

Permuted LeadingOnes has one strict one-bit local optimum and one global
optimum. For every registered `(N, B)` cell the audit reports `B/N²` and the
uniform one-bit probability `1/N` of selecting the first mismatching
coordinate. These are analytic scale diagnostics, not an oracle available to
participants.

## Frozen gates

Construct validity passes only when all of the following hold:

1. the Smooth grid spans `B/N² <= 0.001` and `B/N² >= 1`;
2. mean one-bit NK autocorrelation strictly decreases at every registered K;
3. at least 20 of 24 blocks have lower autocorrelation at K=128 than K=8; and
4. mean K=8 minus K=128 autocorrelation is at least 0.15.

Failure means the nominal grid did not demonstrate the intended difficulty
gradient. Passing establishes only that the tasks range from smoother/easier
to less correlated/harder. It is neither evidence for multi-island search nor
permission to weaken the separately registered performance thresholds.
