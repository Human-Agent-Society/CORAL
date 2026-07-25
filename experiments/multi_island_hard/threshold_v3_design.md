# N=256 social-learning phase study

## Research question

The original N=20 controls and N=128 threshold v2 remain black-box sanity
checks. Version 3 asks a more precise question:

> At what combination of landscape ruggedness, evaluation budget, and
> visible-champion imitation does multi-island search begin to outperform a
> globally visible population?

Harder landscapes alone cannot answer that question. If globally connected
agents continue independent lineages, the failure mode asserted by the blog
never occurs. Version 3 therefore varies and measures social learning instead
of assuming full champion takeover.

## Frozen tasks and budgets

Both held-out tasks use N=256 and eight confirmation seeds disjoint from the
eight calibration seeds:

| task | K | role |
| --- | ---: | --- |
| `smooth256_rep_v3` | 0 | unique-optimum exploitation control |
| `rugged256_k32_rep_v3` | 32 | held-out many-basin stress test |

The registered budget ladder is 256, 512, 1,024, 2,048, 4,096, and 8,192 real
evaluations. Eight agents receive equal quotas. Migration checks occur at each
quarter-budget boundary, with no cadence clipping, so budget does not silently
change the intended number of migration opportunities.

Topologies remain `global_8`, `partition_4`, `multi_island_2`, and
`multi_island_4`. The four-way partition separates boundary effects from
migration, while two versus four islands gives an island-count dose.

## Mechanism calibration

`calibrate_threshold_v3_social.py` uses the exact SHA-based adjacent NK
fitness and actual move-not-copy migration. Each simulated agent mutates its
own incumbent or, with probability p, the best incumbent visible in its
current island. The calibration sweeps p=0/.25/.5/.75/1.

`threshold_v3_social_phase_map.json` freezes the complete K=0/K=32 phase map
over all six budgets and five imitation levels (32 paired policy runs per
cell). `threshold_v3_social_calibration.json` adds K=24/K=48 boundary checks at
4,096 and 8,192 so K=32 is not selected from a one-ruggedness search.

At p=0 all topologies must be exactly identical under paired random streams;
this is an executable null invariant. The full-diffusion p=1 endpoint is an
explicit positive control used to select a sensitive K/budget anchor. Natural
LLM runs are never presumed to have p=1: inferred cross-agent parent adoption,
active lineage count, mutation-operator entropy, and coordinate overlap are
reported as manipulation checks.

Exploratory calibration located the first stable reversal around K=32 and
B=4,096 under full diffusion. The frozen full calibration must reproduce a
positive `multi_island_4-global_8` effect, a rugged-minus-smooth interaction,
and a positive `multi_island_4-partition_4` contrast before LLM confirmation
can use that anchor.

The frozen phase map does reproduce a sharp conditional boundary. At p=0 all
effects are exactly zero. At p=.25, multi-island is worse than global at every
budget. At p=.5 the mean turns positive only at 4,096/8,192 but both intervals
include zero; p=.75 likewise never passes. At p=1 the K=32 contrast changes
from +0.064 SD at 2,048 (interval includes zero) to +0.547 SD at 4,096
(0.312–0.770) and +0.613 at 8,192 (0.404–0.820). Thus the anchor is a
high-diffusion phase transition, not a generic effect of making NK larger.

## Out-of-selection falsification

The selected anchor is not treated as self-validating. A separate audit uses
eight newly generated landscapes, eight paired stochastic policies per
landscape, and a cluster bootstrap whose unit of inference is the landscape
seed. `threshold_v3_robustness.json` records two failures of a broad reading:

* `multi_island_4-global_8` remains positive for one-bit local search
  (+0.452 random SD, cluster interval 0.322–0.598), the registered 1/2/4 mix
  (+0.254, 0.090–0.402), and a broader local mix (+0.249, 0.082–0.427), but
  reverses for fixed four-bit mutation (−0.266, −0.426–−0.113). The boundary
  is therefore operator-conditional.
* Elite, fixed-identity, and worst-resident migration all have small positive
  means versus permanent four-way partition, but every cluster interval
  includes zero. Elite selection is not better than the two non-elite
  controls. The fresh landscapes support an island-boundary effect relative
  to global champion imitation; they do not yet identify a migration benefit
  or a benefit from selecting the strongest migrant.

Consequently the K=32/B=4,096 cell remains a mechanism probe, not sufficient
evidence for the blog's migration claim. A real escalation must report the
realized mutation operator and must add a matched non-elite/sham migration
control before attributing any score difference to selective migration.

## Natural and high-diffusion LLM conditions

The natural protocol does not instruct agents to copy or preserve diversity.
It estimates endogenous social learning. The high-diffusion protocol is a
separate mechanism-positive manipulation: every agent searches around its
current island-visible champion. Results are never pooled across these policy
conditions.

A score advantage without the registered behavior change is non-diagnostic.
Conversely, a natural-policy null with eight inferred lineages still active is
not evidence against islands; it says the treatment did not encounter the
centralizing regime. The primary mechanistic claim requires:

1. high diffusion collapses active lineages faster in `global_8` than in
   `multi_island_4`;
2. on Rugged, `multi_island_4-global_8` is positive and larger than the same
   contrast on Smooth;
3. Rugged `multi_island_4-partition_4` is positive, showing that selective
   migration adds value beyond isolation;
4. the natural-policy result is reported at its observed adoption rate rather
   than relabeled as a full-diffusion test.

The study still measures a controlled optimization mechanism, not semantic
institution-building. Kernel Builder and additional structured code/research
tasks remain necessary for the blog's broader claim.
