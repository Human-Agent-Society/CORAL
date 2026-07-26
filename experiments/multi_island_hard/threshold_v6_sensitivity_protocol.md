# v6 outcome-free design-sensitivity audit

## Purpose

The v6 phase maps test many Rugged cells: the already-running original uses 24
paired blocks, while the superseding extreme extension uses 64. A multiplicity-
controlled null result is not automatically evidence that a practically
relevant effect is absent: that interpretation also depends on paired-block
dispersion. This audit freezes the sensitivity report while both phase-map raw
files are absent. It reads no landscape, score, topology, or held-out seed.

## Frozen calculation

For the original 25-cell v6 Rugged map with 24 blocks and the superseding
12-cell extreme extension with 64 blocks, the audit uses the exact registered
one-sided Bonferroni alpha `0.05 / (cells * 2 contrasts)` and paired-effect
standard-deviation scenarios `0.25, 0.50, 0.75, 1.00` in within-landscape
random-SD units.

For both registered practical floors (`multi-global = 0.25` and
`multi-partition = 0.10`), it reports:

- normal-approximation power at the floor;
- the minimum detectable effect for 80% power; and
- the number of paired blocks required for 80% power at the floor.

This is a transparent design diagnostic, not a replacement test and not a
reason to alter the frozen phase-map gates after seeing results.

## Interpretation rule

A passing registered gate remains positive scripted-mechanism evidence. A
failed gate means the registered positive claim did not pass. It may be
described as evidence against effects large enough for the design to detect,
but it must not be described as proof of no practically relevant effect when
the observed paired-block dispersion is in a low-power region identified by
this audit. Natural-agent, CORAL-anchor, and external-task requirements are
unchanged.
