# N=512 threshold-v4 registered calibration result

## Scope and integrity

The complete frozen calibration finished on 2026-07-25. It contains all 168
registered summaries from N=512, K=0/16/32/64/128,
B=4,096/8,192/16,384, four mutation policies, three topology conditions,
eight independent landscape clusters, and four paired stochastic policies per
landscape. Every summary contains 32 paired policy runs and uses the landscape
as the bootstrap unit.

The retained result is `threshold_v4_scale_calibration.json` (SHA-256
`079da31f5fe728275afc46244c27606fc23eb475aebdca34cb6efc3cc0c8518d`).
`fully_registered_run` is true; no reduced screen or participant outcome was
used in the decision.

## Registered thresholds

| estimand | earliest passing cell | interpretation |
| --- | --- | --- |
| boundary (`multi_island_4-global_8` plus Rugged-minus-Smooth) | K=32, B=8,192 | selected for the first high-diffusion held-out pilot |
| migration (`multi_island_4-partition_4`, conditional on boundary pass) | K=64, B=16,384 | operator-side threshold only; not substituted for the frozen first-pilot selection |
| fixed four-bit generalization | none | rejects an operator-universal multi-island claim |

At the selected boundary cell, the three registered local mutation policies
have the following random-SD contrasts:

| mutation | multi-global | Rugged-minus-Smooth interaction | multi-partition |
| --- | ---: | ---: | ---: |
| one-bit | +0.566 [0.443, 0.681] | +0.664 [0.539, 0.780] | +0.225 [0.018, 0.407] |
| registered mixed | +0.332 [0.028, 0.631] | +0.466 [0.167, 0.770] | +0.045 [-0.147, 0.311] |
| broader local | +0.265 [0.003, 0.488] | +0.542 [0.290, 0.771] | +0.266 [0.124, 0.402] |
| fixed four-bit | -0.507 [-0.728, -0.315] | +0.740 [0.528, 0.913] | +0.108 [-0.054, 0.258] |

The broader-local boundary lower bound is only slightly above zero, while
fixed four-bit mutation reverses the primary boundary contrast. The pass is
therefore a deliberately narrow local-operator mechanism threshold, not a
robustness claim over arbitrary search behavior. K=32/B=8,192 does not pass
the migration gate because registered-mixed `multi_island_4-partition_4` is
uncertain.

The later K=64/B=16,384 cell is the first migration pass across all three
local policies. Its broader-local boundary interval also nearly touches zero,
and fixed four-bit still fails. It is retained as a separate mechanism result,
not used post hoc to make the first LLM pilot more favorable.

## Held-out landscape audit

`threshold_v4_diagnostics.json` freezes 1,024 random candidates and 32
deterministic greedy starts on each of eight paired held-out Smooth/Rugged
landscapes (SHA-256
`7902948d7eead1301dc2cd65168c071b7daf8aa2dcc95e01a8b703166189ce6b`).
All Smooth landscapes recover one exact one-bit optimum. Every K=32 landscape
ends at 32 distinct maxima from 32 starts. Smooth one-bit autocorrelation is
0.9955–0.9962; Rugged is 0.9292–0.9421. Thus the held-out pair is non-degenerate
and separates the intended local search geometry without exposing a private
seed.

## Staged decision

The active SRT build passed an executable cross-island state/worktree canary,
and all relevant tests passed before launch. The next permitted action is one
held-out high-diffusion repetition at K=32/B=8,192 for Smooth and Rugged under
`global_8`, `partition_4`, and `multi_island_4`. This is an operational and
mechanism pilot, not evidence for the blog. Natural-policy replication,
eight-seed inference, the K=64 migration cell, and broader claims remain gated
on pilot integrity and observed behavior.
