# N=512 operator-robust Smooth/Rugged threshold study

## Why v4 exists

The N=256 v3 study found a real mechanism boundary, but not a general result.
Under full visible-champion imitation, four islands beat one global population
on K=32 for one-bit and several mostly-local mutation mixtures.  Fixed
four-bit mutation reversed the effect, and elite migration did not separate
from permanent partition or non-elite movement.  The one-seed real-agent
Smooth pilot also showed the expected cost of retaining lineages, but cannot
locate a Rugged threshold.

Version 4 therefore makes both controls materially harder while treating
operator sensitivity as a factor rather than a nuisance to hide.  It asks two
separate questions:

1. **Boundary threshold:** when do four communicating islands beat one global
   visibility pool specifically on Rugged rather than Smooth?
2. **Migration threshold:** when do those islands also beat the identical
   four-way boundary with migration permanently disabled?

A boundary-only result is never described as evidence for selective
migration.  These remain synthetic mechanism tests, not substitutes for
Kernel Builder, Circle Packing, or another structured real task.

## Harder landscape family

All variants use the same adjacent private-seed NK construction and a literal
candidate, with no assigned coordinates, modules, certificates, or offline
artifact union.  Dimension doubles from N=256 to N=512.  The calibration grid
crosses:

| factor | registered values |
| --- | --- |
| Smooth/Rugged K | 0 / 16 / 32 / 64 / 128 |
| real-evaluation budget | 4,096 / 8,192 / 16,384 |
| mutation policy | one-bit / registered local mix / broader local mix / fixed four-bit |
| topology | global-8 / partition-4 / multi-island-4 |
| calibration landscapes | 8 |
| stochastic policies per landscape | 4 |

K is not treated as a monotone difficulty dial: high K can destroy useful
local signal rather than simply making a task “harder.”  The grid must report
all K values.  Budget is scaled far beyond the earlier 16/24-query controls so
that a null cannot be dismissed as immediate feedback starvation.

## Falsification-first selection

`calibrate_threshold_v4_scale.py` uses full visible-champion imitation as an
explicit positive-control mechanism and real move-not-copy cyclic migration.
Calibration seeds are generated under the
`threshold-v4-scale-calibration` namespace.  The eight future participant
seeds use `threshold-v4-heldout` and are disjoint.

Effects are standardized by the random-candidate SD for each landscape.
Stochastic policy repetitions are averaged within landscape; the cluster
bootstrap resamples landscapes.  Cells are considered in the frozen order
earliest budget, then smallest positive K.

The boundary threshold requires, separately for one-bit, the registered local
mix, and the broader local mix:

1. `multi_island_4 - global_8 >= 0.25` random SD with cluster-bootstrap lower
   bound above zero; and
2. the Rugged-minus-Smooth version of that contrast is also at least 0.25 SD
   with lower bound above zero.

The migration threshold additionally requires
`multi_island_4 - partition_4 >= 0.10` SD with lower bound above zero for all
three local operators.  Fixed four-bit mutation is a registered stress test
with its own reported threshold.  It is not silently dropped if it reverses
the result.

The initial two-landscape/two-policy engineering screen suggested N=512,
K=32, B=8,192–16,384 as a candidate region.  That screen has no inferential
status and cannot select an LLM task; only the complete frozen calibration
file may do so.

## Held-out LLM staging

No participant run starts until the calibration completes.  If no boundary
cell passes, v4 stops as a registered negative result.  If a boundary cell
passes but no migration cell does, the real-agent pilot may test boundary
preservation but cannot be presented as a migration test.

The first real-agent stage is one held-out seed at the selected K/budget under
`global_8`, `partition_4`, and `multi_island_4`.  Smooth uses the same N,
budget, seed, roster, topology order, and participant policy.  Each of eight
agents receives exactly one eighth of the budget.  Migration checks occur at
quarter-budget boundaries with round-robin destinations.  Condition order is
rotated across later seeds rather than always placing multi-island last.

Natural and high-diffusion policies remain separate.  The high-diffusion arm
is a mechanism-positive manipulation; the natural arm measures endogenous
sharing and is never relabeled after observing lineage collapse.  Expansion
to eight held-out seeds requires exact budgets, numeric feedback, paired first
candidates, quota balance, correct private seed, no migration in controls,
realized migration in treatment, and a post-migration evaluation by every
migrant.

Primary performance is paired final-best random-z.  Secondary outcomes are
best-so-far AUC, midpoint/final diversity, inferred active lineages,
cross-agent adoption, transition-radius distribution, mutation-operator
entropy, realized migration ticks, and the two topology contrasts.  A score
advantage without the registered lineage-collapse direction is
non-diagnostic.
