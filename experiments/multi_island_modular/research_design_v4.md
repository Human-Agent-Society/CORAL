# Hard v4 multi-island threshold study

## Status and question

The v1/v2 packages and the v3 hard package are design audits. They must not
be used as evidence for or against institutions. v4 is an independent,
harder candidate package intended to locate a budget interval in which
migration can improve assembly of independently tested modules.

The narrow question is:

> At a fixed total evaluation budget and fixed eight-agent roster, does
> migration between two partially independent islands increase
> provenance-backed assembly relative to partition without migration?

The primary contrast is `multi_island - partition`. `multi_island - global_8`
is a secondary contrast with the same eight-agent roster. The original
four-agent `global` condition remains a reference, not a clean causal
contrast.

## v4 task construction

Both tasks use 24 contiguous 24-bit modules (576 bits total), a private seed
bundle, and active-module-only feedback. The candidate is preferably a tuple
of 24 literal strings. A legacy 576-bit string is accepted only for parser
compatibility; the seed candidate and protocol use tuples to avoid manual
length errors consuming the experimental budget.

The smooth task returns Hamming-match feedback. A conservative coordinate
probe needs `24 * (24 + 1) = 600` evaluations to identify every module. It is
a low-epistasis control: a null migration effect is expected and is not a
general null result about institutions. The planned smooth ladder is 384 /
768 / 1,536, with 384 below the anchor and 768 as the first threshold
candidate.

The rugged task has a public 512-entry 24-bit codebook. The private target is
the first of 24 entries in a seed-specific permutation, so targets are unique
within each repetition. All-zero scores 0.78, non-target nonzero codes score
0.43, and the exact target scores 1.0. Ordered enumeration costs 4,530–8,522
evaluations across the frozen eight-seed bundle (mean 6,699.25). The planned
rugged ladder is 3,072 / 6,144 / 8,192; lower budgets are calibration pilots.

## Controls and gates

Every task/budget/topology cell uses eight paired seed repetitions. The
topologies are:

* `global`: one island with four agents;
* `global_8`: one island with eight agents;
* `partition`: two islands with four agents each and no migration;
* `multi_island`: two islands with four agents each and migration enabled.

Migration cadence is `max(16, min(64, budget // 8))`. The analyzer rejects a
cell with a wrong mode/seed/budget/topology, a private-bundle mismatch, a
grader/tune attempt, a malformed real candidate, a non-numeric score, or a
missing migration event in a multi-island cell. A complete cell must also
select at least eight distinct modules; otherwise the result is reported as
an allocation failure rather than topology evidence.

The primary outcomes are final provenance-backed exact-module count and
assembled score. Pooled provenance, assembly gap, module coverage, and
migration count are diagnostics. No oracle recomputation of untested bits is
used as primary evidence.

## Staged execution

The full budget ladder is a preregistered search space, not a promise to run
every cell. To keep the study feasible, execute sequentially:

1. Run one paired seed at a low pilot budget (currently `B=32`) for
   `global_8`, `partition`, and `multi_island`; use it only to check parser,
   score range, coverage, and migration mechanics.
2. Run one paired smooth budget near the first nonzero-assembly threshold
   (start with `B=128`), then repeat only the first budget whose three
   topologies pass all gates.
3. Run rugged calibration pilots at `B=1024` and `B=2048`; choose the first
   budget with nondegenerate scores and at least four modules per island
   before expanding to paired repetitions.
4. Use three repetitions to estimate a pilot contrast and eight only for a
   pre-registered confirmatory budget. Never pool cells from different package
   versions or promote a rejected coverage cell to evidence.

## Falsifiers and interpretation

* If `multi_island` does not exceed `partition` in the rugged threshold
  interval, that is evidence against this migration policy under this
  protocol, not a universal claim that institutions do not help.
* If all conditions saturate together on smooth, that validates the
  separable-control prediction.
* If coverage gates fail, the experiment measures search-allocation or agent
  protocol failure and must be redesigned before interpreting topology.
* If rugged cells remain at zero exact modules through 8,192, the package is
  still underpowered; reduce codebook size or module count only in a new
  preregistered version.
