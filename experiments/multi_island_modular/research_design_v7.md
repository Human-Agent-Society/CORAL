# Hard v7 oracle-free threshold study

> **Status: superseded design audit. Do not launch the registered matrix.**
> Post-pilot review found that the primary `final_known_blocks` outcome pools
> discoveries across islands, giving `partition` an operator-side assembly it
> could not perform during the run. The deterministic disjoint lanes and
> separable objectives also make exact discovery nearly topology-invariant.
> v7 therefore validates evaluation, quota, migration, and provenance
> plumbing only; it cannot identify a multi-island advantage.

## Research question

The v6 pilot increased the search space but still returned an inactive-module
assembly count on every evaluation. v7 asks a narrower, cleaner question:

> At what total feedback budget does migration allow two isolated communities
> to assemble more independently verified modules than the same partition
> without migration?

This is a black-box allocation/transfer mechanism study. It is not, by itself,
evidence for semantic collaboration or institution-building.

## Task construction

Both tasks use 48 contiguous modules, now widened from 32 to 64 bits. The
grader scores only `ACTIVE_MODULE` and returns only its score plus a tested
flag. No inactive-module count, assembly bonus, or scalar global assembly
signal is exposed during search. Exact assembly is computed offline in
chronological order from real active evaluations and provenance.

* `smooth_hard_v7` is a separable Hamming control. A coordinate/provenance
  oracle needs `48 * (64 + 2) = 3,168` evaluations for a complete artifact.
* `rugged_hard_v7` is an equality-only control with a public 4,096-entry,
  64-bit codebook and a private per-seed permutation. The calibrated ordered
  full-artifact cost is 80,146–111,613 evaluations (mean 100,624.625).

The only intended difference from v6 is higher search difficulty and removal
of the feedback-side assembly oracle. Neither task has semantic interfaces or
epistasis; they remain controls for search allocation and verified state
transfer.

Malformed agent candidates receive numeric score 0 and consume a normal real
evaluation. The analyzer permits at most one malformed attempt in a completed
cell and reports its commit. This treats a single formatting error as agent
performance rather than a grader outage, while preventing a cell with repeated
invalid output from entering a topology contrast.

## Pre-registered ladder

| task | budgets | idealized purpose |
| --- | ---: | --- |
| smooth | 1,024 / 2,048 / 3,072 / 4,096 / 6,144 / 8,192 | below, near, and above the 3,168 anchor |
| rugged | 16,384 / 32,768 / 65,536 / 98,304 / 131,072 / 196,608 | below, around, and above the 100.6k ordered anchor |

The idealized oracle is calibration only. A cell is not evidence unless it has
the declared real budget, numeric feedback for every attempt, at least 16
distinct active modules, at least 8 origin modules from each multi-island
community, at least one exact active discovery, and a real migration event in
the multi-island condition.

Because the LLM runtime can allocate attempts unevenly, the runner atomically
caps every agent at exactly one eighth of the total real-evaluation budget.
A complete cell therefore requires all eight agents to contribute the same
number of real attempts. The analyzer verifies both the launch override and
the observed per-agent counts; a quota-failing cell remains an operational
audit, never a topology result.

## Topologies and primary contrast

`global_8`, `partition`, and `multi_island` all use eight agents and paired
seed indices. `partition` has two four-agent islands and no migration;
`multi_island` has the same partition with migration; `global_8` is the
one-island secondary control. The primary contrast is the final
provenance-backed exact-module count:

```text
multi_island - partition
```

Secondary outcomes include best single-candidate assembly, pooled discovery,
assembly gap, transfer events, transferred blocks, module coverage, duplicate
query rate, and agent-balance diagnostics. The expected pattern is a possible
positive window only after enough budget exists for both communities to find
complementary modules but before partition saturates. Smooth is a negative
control and need not show a positive contrast.

The standard roster follows deterministic module lanes `base_index + 8*k`.
Agents advance after an exact result or after exhausting the 66-evaluation
Smooth coordinate allowance on a module. This makes coverage a protocol
property rather than relying on eight independent LLMs to negotiate the next
uncovered index correctly.

## Interpretation safeguards

1. The v7 feedback change prevents inactive exact-count differential probing.
2. All score-ranked migration and candidate reuse are still black-box
   mechanisms; a positive contrast does not establish institutions.
3. Before a blog claim, run communication ablations: no migration, candidate
   only, verified-claim digest only, and candidate plus digest. The source and
   destination reuse metrics must agree with the assembly outcome.
4. A zero-exact, coverage-failing, or quota-failing cell is underpowered or
   operationally invalid, not evidence against multi-island coordination.
