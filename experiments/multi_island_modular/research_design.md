# Multi-island modular threshold study

## Status and question

The original NK and modular-v1/active-v2 runs are stress tests and design
audits. They do not support a positive or null claim about institutions. The
current research question is narrower:

> Under a fixed total feedback budget, at what task difficulty does migration
> improve the assembly of independently tested modules over two isolated
> communities?

Positive evidence supports transfer of tested building blocks under this
protocol only. It does not establish semantic collaboration on real code or
research artifacts.

## v3 task construction

Both v3 tasks use sixteen contiguous 16-bit modules (256 bits total), the same
candidate parser, hidden seed bundle, active-module interface, and topology
settings. Each evaluation returns only the score for the declared
`ACTIVE_MODULE`; the full artifact is never returned through the feedback
channel.

The smooth task derives one hidden 16-bit target per module and returns the
Hamming-match score. The wider modules and doubled module count make a simple
coordinate-probe baseline cost 272 evaluations for one complete artifact.

The rugged task derives a private target index per module into a public 256-code
16-bit codebook. All-zero scores 0.72, every non-target nonzero code scores
0.45, and the exact target scores 1.0. There is no gradient, but the search
domain and its ordered-enumeration cost are explicit and reproducible. Across
the eight seed bundle entries, the complete-artifact anchor is 1,238–2,395
evaluations (mean 1,936).

The operator's primary metric is provenance-backed assembly. A module becomes
known only when a real evaluation selected it and returned exactly 1.0. A later
candidate receives credit for that module only if it carries the same tested
bits. This prevents untested random bits from becoming hidden-answer credit.
The old oracle artifact score remains available as a secondary diagnostic.

## Matrix and controls

The planned v3 budget ladder is:

* smooth: 256, 512;
* rugged: 1,024, 2,048, 4,096.

Every task/budget/topology cell uses eight independent seed repetitions, with
the same seed index paired across global, partition, and multi-island cells.
Every cell has exactly its declared number of finalized real evaluations and no
grader errors. Migration cadence is `max(16, budget/4)`.

`global` has one island with four agents, `partition` has two islands with four
agents each and no migration, and `multi_island` has the same two-island roster
with migration enabled. Therefore `multi_island - partition` is the clean
primary migration contrast; `multi_island - global` is secondary and includes
the agent-count/topology difference.

Primary outcomes are final provenance-backed exact-module count and assembled
score. The pooled-provenance score (all exact modules discovered anywhere in
the run) is reported beside the best single-candidate score; their gap
distinguishes discovery failure from assembly/transfer failure. Secondary
outcomes are adjacent tested pairs, assembled best-so-far AUC, latest-candidate
diversity, migration count, oracle score, and protocol errors.

## Predictions and falsifiers

* Smooth should show a discovery threshold around the 272-evaluation anchor.
  If all topologies saturate together, that is a valid result that migration is
  unnecessary for this low-epistasis control.
* Rugged should remain near the all-zero trap at low budgets and begin showing
  tested modules in the 1,024–2,048 region. A positive multi-island contrast is
  expected only after enough budget exists for separate communities to find
  different modules and migration to carry one candidate across.
* If all rugged topologies remain at zero tested blocks through B=4,096, the
  model/task pair is underpowered; lower the codebook size or module count
  before interpreting a null topology contrast.
* If partition and multi-island are indistinguishable after the integrity and
  provenance checks, the result is evidence against this migration policy for
  this protocol, not a universal claim that institutions do not help.

## Required audit gates

No v3 result enters the blog as evidence until:

1. all eight seed repetitions pass private-bundle and exact-real-attempt gates;
2. the analyzer reports no parse errors, grader errors, or budget overshoot;
3. the primary provenance metric and the oracle diagnostic agree on the
   direction of any claimed effect;
4. the smooth and rugged threshold pilots show non-degenerate score ranges;
5. the human author reviews the complete diff and the exact test commands.
