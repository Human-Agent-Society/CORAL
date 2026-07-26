# Preregistered selected-cell confirmation

## Why this stage exists

The 64-block extreme phase map is adequately sensitive to a moderate
`multi-global` effect, but its cell-wise Bonferroni analysis has only about
10% power for a `multi-partition = +0.10` random-SD effect when the paired
block SD is 0.5. A failed migration-control gate would therefore remain
ambiguous. This defect was identified while the extreme raw, analysis,
selection, and confirmation artifacts were all absent.

The unchanged 64-block grid is now a discovery phase map. It still answers
where effects appear on the `(K, budget)` surface, but it cannot by itself
support the final positive scripted-mechanism claim. One cell is selected by
a frozen rule and tested on 192 new paired landscape-policy blocks.

## Frozen selection rule

For each of the 12 extreme Rugged cells, compute discovery point estimates for
`multi-global` and `multi-partition` in that landscape's random-reference SD
units, plus the registered search-progress margin.

1. Prefer cells whose point estimates are at least `+0.25` and `+0.10`
   respectively and whose three topologies clear the search-progress gate.
2. Among those cells, maximize the smaller effect surplus over its practical
   floor, then the progress surplus; use lower `K` and lower budget only as
   deterministic tie-breakers.
3. If no cell is eligible, select the cell maximizing the smaller of its
   effect and progress surplus, with the same tie-breakers.

Discovery confidence bounds never enter selection. The rule always produces
one cell, so confirmation cannot be cancelled merely because the discovery
surface is disappointing.

## Confirmation design

- Rugged `N=128`; `K` and budget come only from the frozen selector.
- Global, four permanent partitions, and four migrating islands use exactly
  the same mechanism and mutation policy as the discovery map.
- 192 fresh paired blocks use the namespaces
  `threshold-v6-extreme-confirmation-heldout` and
  `threshold-v6-extreme-confirmation-policy`, with fail-closed overlap checks.
- Each block has a separate 512-sample random-reference mean and SD.
- Execution checkpoints atomically every 24 condition runs. Only
  completed/expected counts may be inspected before all 576 runs finish.

The outcome-free power audit models the actual per-contrast gate: the point
estimate must meet its practical floor and the one-sided 95% lower bound must
exceed zero. With 192 blocks, an effect 0.05 SD above either floor has at least
80% approximate component power for paired-effect SD up to 0.75.

## Decision and error control

The selected cell passes only if:

1. `multi-global` has mean at least `+0.25` random SD and a one-sided 95%
   lower bound above zero;
2. `multi-partition` has mean at least `+0.10` random SD and a one-sided 95%
   lower bound above zero; and
3. every topology's mean gain over random exceeds the equal-budget iid-normal
   expected maximum plus 0.25 SD.

The positive claim is a conjunction: both effect nulls must be rejected.
Testing each component at one-sided alpha 0.05 is an intersection-union test;
under the union null, the probability of rejecting both is bounded by the
size of the false component. No correction across discovery cells is needed
because the confirmation data are independent of cell selection.

## Claim boundary

A pass confirms one region for the frozen scripted mechanism; the discovery
surface supplies the provisional threshold map. It still does not establish
that natural coding agents or institutions benefit. The audited CORAL anchor,
natural-agent arm, and Circle Packing external validation remain mandatory.
Failure is not evidence of absence when the observed paired-effect dispersion
falls outside the preregistered sensitivity range.
