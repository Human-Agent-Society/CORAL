# Hard v6 verified-assembly threshold study

## Question

The v5 package made the landscape harder, but its primary assembly metric was
operator-side reconstruction: the grader only rewarded the active module.
That makes a topology effect difficult to interpret. v6 asks a narrower and
observable question:

> At a fixed eight-agent feedback budget, is there a difficulty interval in
> which two isolated communities plus selective migration produce more
> verified artifact assembly than the same partition without migration?

This remains a mechanism study, not a universal claim about institutions.

## Task construction

Both tasks use 48 contiguous 32-bit modules (1,536 bits), eight paired hidden
seeds, and active-module local feedback. Unlike v5, every grader response also
contains an `artifact_exact_count`: each exact module carried by the complete
candidate contributes an assembly reward. The reward is exact-only for
inactive modules, so it makes assembly an actual task objective without
revealing per-bit gradients for modules that were not selected.

The returned score is:

```text
0.55 * active_module_score + 0.45 * artifact_exact_count / 48
```

The analyzer still keeps a chronology-backed provenance ledger. An exact bit
pattern that was never actively tested is not counted as a verified discovery,
even though the grader's exact-only assembly reward makes such a coincidence
vanishingly unlikely.

* `smooth_hard_v6` is the separable control. Hamming feedback has a
  48 × 34 = 1,632 evaluation coordinate/provenance anchor.
* `rugged_hard_v6` uses a public 2,048-entry codebook and a private
  per-seed permutation. Wrong nonzero proposals score 0.10, the all-zero
  decoy scores 0.08, and exact targets score 1.0. Ordered full-artifact
  enumeration costs 45,540–57,482 evaluations over the frozen seeds (mean
  51,512.75).

The rugged task is still intentionally a black-box allocation control. It is
not evidence of semantic collaboration by itself; the transfer diagnostics and
communication ablation are required for that interpretation.

## Budget ladder and predictions

The pre-registered ladder is:

| task | budgets | purpose |
|---|---:|---|
| smooth | 512, 1,024, 1,536, 2,048, 3,072 | below, near, and above the 1,632 anchor |
| rugged | 8,192, 16,384, 32,768, 49,152, 65,536 | below and around the 51.5k ordered anchor |

`global_8`, `partition`, and `multi_island` each use eight agents and the
same paired seed. The primary contrast is `multi_island - partition`; the
secondary contrast is `multi_island - global_8`.

The prediction is not that multi-island must win everywhere:

* Smooth should remain a negative control or show a small migration cost.
* Rugged should first show a discovery threshold and then, if transfer works,
  a window in which the pooled exact count and observed assembly reward in
  multi-island exceed partition.
* A zero-exact or coverage-failing cell is underpowered/calibration failure,
  never evidence against migration.
* If all topologies saturate together, that is a valid null for this task and
  budget, not a universal null about institutions.

Migration cadence is `max(128, min(512, budget // 4))`, with a 128-evaluation
cooldown. This leaves enough time to complete a module probe while retaining
several transfer opportunities in rugged cells.

## Mechanism and measurement

The analyzer reports both actual and reconstructed outcomes:

* `observed_artifact_exact_max` and `observed_artifact_score_max` come from
  the grader feedback and are the primary task outcomes;
* `final_known_blocks`, `best_tested_blocks`, and pooled provenance remain
  chronology-backed diagnostics;
* `transfer_events` and `transferred_blocks` count exact modules carried into
  a different current island after their discovery origin;
* `origin_island_coverage` uses attempt-level origin metadata. Migration now
  preserves `origin_island_id` instead of reassigning historical discoveries
  to the destination island.

No cell enters a topology comparison unless it has the declared real budget,
valid paired seed and mode, numeric feedback for every attempt, at least 16
distinct active modules, at least 8 modules originating on each multi-island
community, at least one exact signal, and (for multi-island) at least one
observed migration event. These gates are calibration safeguards, not ways to
discard an inconvenient result after looking at the outcome.

## Required follow-up ablation

The v6 task can show whether migration plus an observable assembly objective
helps. It still cannot identify whether the mechanism is candidate state,
agent memory, or explicit community knowledge. Before a blog claim, run:

1. partition without migration;
2. migration carrying only the selected agent/candidate;
3. migration plus an explicit source-island verified-claim digest;
4. global_8 as the one-pool control.

The source/destination exact-module reuse metric must move in the same
direction as the actual assembly reward. Otherwise the result is an
allocation or restart effect, not evidence for knowledge transfer.
