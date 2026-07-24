# Budget–difficulty threshold design

The original 20-bit Smooth/Rugged pair cannot identify a migration threshold.
This protocol varies query budget separately from landscape difficulty, so a
null result is not automatically interpreted as evidence against migration.

## Cells

The primary confirmatory matrix uses two frozen, independently seeded
landscapes:

| family | N | K | interpretation |
| --- | ---: | ---: | --- |
| smooth128 | 128 | 0 | separable control |
| rugged128_k24 | 128 | 24 | strong local epistasis |

Each family is run at budgets **24, 64, and 128** finalized real evaluations.
Each budget has the same three topology conditions: `global`, `partition`, and
`multi_island`. There are three operational repetitions per cell, giving 54
cells. The agent model, prompts, sandbox, task seed, and topology boundary are
held fixed. Migration runs every
`budget / 4` real evaluations (rounded down, minimum 6), so each treatment has
four planned opportunities to exchange agents.

The `rugged128_k4` and `rugged128_k12` landscapes remain secondary difficulty
interpolation points. They are useful for plotting a K slope, but the primary
claim does not depend on choosing a favorable intermediate K. The primary
matrix has 54 cells and 3,888 finalized real evaluations.

## Analysis

The primary outcome is the within-landscape, within-budget contrast

```text
multi_island reference_gain − global reference_gain
```

where `reference_gain` is normalized by a fixed operator-side multi-start
greedy reference. It is not an estimate of the global optimum. The same
contrast is computed against `partition` to separate migration from isolation.
Best-so-far AUC, random-baseline z-score, final diversity, null rate, and
runtime/API errors are secondary diagnostics.

The predeclared practical threshold is a positive contrast of 0.05 reference-
gain units with a replicate-bootstrap interval whose lower bound is above
zero. The earliest budget satisfying that rule is the operational threshold;
if no budget satisfies it, the result is a null threshold rather than a claim
that migration is universally ineffective. Raw scores are never compared
across the two landscapes.

## Integrity gates

The producer-side real-budget gate admits at most the declared number of
queued or finalized real attempts, even when four agents submit concurrently.
Every accepted cell must have exactly its declared count, no grader errors,
matching private taskdata, the hard role protocol, and zero migration notes in
the non-migration controls. Cells failing any gate are excluded before
analysis and reported in the audit.

This is still a black-box optimization experiment. It tests whether migration
helps under a controlled feedback budget; it does not by itself establish
semantic collaboration or provenance reuse. A separate modular artifact task
is required for that claim.
