# Hard v5 multi-island threshold study

## Question

The v4 package was still too close to a low-dimensional allocation pilot. v5
asks a narrower, falsifiable question:

> At a fixed total evaluation budget and fixed eight-agent roster, is there a
> difficulty interval in which migration improves provenance-backed assembly
> over the same two-island partition without migration?

The primary contrast remains `multi_island - partition`; `global_8` is the
same-roster one-island control. A positive result is conditional on this
protocol and does not establish a universal institution effect.

## v5 task construction

Both tasks use 32 contiguous 32-bit modules (1,024 bits), active-module-only
feedback, and eight paired private seeds.

* `smooth_hard_v5` returns deterministic Hamming feedback. A coordinate search
  needs 32 × 33 = 1,056 probes to identify all modules and one additional exact
  submission per module for provenance, giving a 1,088-evaluation full-artifact
  anchor. It is a high-dimensional separable negative control: migration is
  expected to be unnecessary once feedback is sufficient.
* `rugged_hard_v5` uses a public 1,024-entry 32-bit codebook and a private
  per-seed permutation. Every non-target nonzero code scores 0.42, the public
  all-zero decoy scores 0.38, and the exact target scores 1.0. The decoy is
  intentionally below a normal failure so the score-ranked migration policy
  does not systematically move agents that have stopped exploring. Targets
  are unique within a seed. Ordered enumeration costs are calibrated before
  agent runs; they are expected to be roughly 13k–19k evaluations for a full
  artifact across the frozen seeds.

The codebook and scoring rules are public through the grader source. Only the
seed and target permutation remain private. This makes difficulty reproducible
without exposing an answer key.

## Budget ladder and staged execution

The ladder is a search space, not a promise to run every cell:

| task | budgets | purpose |
|---|---:|---|
| smooth | 256, 512, 1,024, 1,536 | below, near, and above the 1,088 full-artifact anchor |
| rugged | 4,096, 8,192, 16,384, 24,576 | below, near, and above the ordered-enumeration anchor |

An idealized breadth-first codebook oracle would find roughly 4.5 / 8.5 /
16.4 / 24.8 of the 32 rugged modules at those four budgets (seed range is
reported in `hard_v5_calibration.json`). A serial smooth oracle would identify
roughly 7 / 15 / 30 / 32 provenance-tested modules at 256 / 512 / 1,024 /
1,088 evaluations. These are calibration references, not agent performance
claims or upper bounds.

First run one paired seed at the lowest budget for `global_8`, `partition`,
and `multi_island` to validate parser, score range, coverage, and migration.
Then run one repetition at the first budget where all three topologies have
nondegenerate scores, at least 12 distinct modules, and at least 6 modules per
island for multi-island. Only that budget is expanded to three pilot
repetitions, and only a pre-registered budget with a clean pilot is expanded
to eight confirmatory repetitions.

Migration cadence is `max(32, min(128, budget // 32))`, giving roughly four
global attempts per agent between treatment opportunities while capping
restart overhead. The same cadence and four grader workers are used in every
topology. `global_8`, `partition`, and `multi_island` each use eight total
agents; partitioned conditions therefore have four agents per island. The
eight-agent roster is held fixed in the primary comparison.

## Integrity and outcomes

The analyzer rejects wrong topology/mode/seed/budget, private-bundle mismatch,
grader or tune attempts, malformed candidates, non-numeric scores, degenerate
score ranges, insufficient module coverage, missing migration events, and cells
with no provenance-backed exact module. A cell with zero exact modules is kept
as a calibration failure, never as a topology result.

Primary outcomes are provenance-backed exact-module count and the best
single-candidate assembled score. Pooled provenance and the assembly gap are
diagnostics. For rugged, a raw assembled score near 0.38 is the decoy baseline
and must not be interpreted as discovered knowledge.

## Construct-validity safeguards

The v5 rugged task is equality-only and therefore still tests black-box
allocation more than semantic collaboration. It is deliberately paired with a
future communication ablation: partition, agent migration, and migration plus
an explicit source-island claim digest. Those treatments are required before
claiming that migration transfers community knowledge rather than merely
moving a high-scoring agent.

If all topologies saturate together on smooth, that supports the separable
control prediction. If rugged remains at zero exact modules at 24,576, the
package is underpowered and no topology conclusion is allowed. If coverage
gates fail, the result is an allocation/protocol failure, not evidence against
institutions.
