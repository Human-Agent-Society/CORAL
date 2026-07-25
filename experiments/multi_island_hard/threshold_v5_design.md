# Hard-Smooth/Rugged topology threshold v5

## Question and claim boundary

Version 5 asks when a fully specified visible-champion social-learning policy
benefits from multi-island visibility on a genuinely hard search problem.  It
does not treat the earlier 32-evaluation canary, the offline simulator, or one
held-out seed as evidence for the blog's institutions claim.

The design separates three explanations that the earlier synthetic pair could
not cleanly distinguish:

1. **easy versus hard:** the additive K=0 control saturates by B=16,384;
2. **single path versus multiple basins:** a hard task need not reward islands;
3. **boundary preservation versus migration:** multi-island must be compared
   with both global visibility and permanent partition.

## Landscapes

Both tasks use N=512 literal candidates, eight paired private seeds, identical
topology-invariant initial candidates, and the same mutation schedules.

The new hard Smooth control is hidden-target, hidden-coordinate-order
**Permuted LeadingOnes**.  Its score is the fraction of the prefix matching a
private 512-bit target when coordinates are read in a private seeded
permutation.  Every non-optimal candidate has exactly one improving one-bit
coordinate and the exact target is the only strict one-bit local optimum, but
the scalar score does not reveal which coordinate comes next.  Blind local
mutation therefore follows a long plateaued path: at the complete
calibration's largest budget, the registered mixed policy solved a mean of
71.2 prefix bits, at most 91, and never reached the 512-bit optimum in 32
policy runs.

Rugged uses the same adjacent hidden-seed NK construction as v4.  The frozen
operator-robust calibration selects K=64/B=16,384; K=128 remains a registered
stress task, not a post-hoc replacement.

Permuted LeadingOnes and NK have very different random-baseline variances.
Their random-z effects are therefore never subtracted.  Ruggedness specificity
is gated by the original within-NK K64-minus-K0 interaction.  Permuted
LeadingOnes is a separate directional negative control: it must be unsolved
and global must beat multi-island for every registered local operator.

After task selection and before confirmatory interpretation,
`diagnose_threshold_v5.py` freezes diagnostics for the actual eight held-out
seed pairs. Every Smooth instance must retain its analytically exact unique
strict one-bit optimum; every Rugged instance must produce at least 24 distinct
local maxima from 32 deterministic greedy starts, and its one-bit
autocorrelation must be below every hard-Smooth instance. These are difficulty
gates, not topology outcomes, and cannot rescue a failed contrast.

## Mechanism arm

The scripted arm uses eight agents and a registered mutation mix: 90% one-bit,
8% two-bit, and 2% four-bit proposals.  Every proposal mutates the best
currently visible per-agent champion.  The controller runs through ordinary
CORAL worktrees, commits, `coral eval`, grader admission, island isolation,
migration, and restart.  It never calls the grader directly or uses an LLM.

| condition | islands | migration |
| --- | ---: | --- |
| global | 1 | disabled |
| partition | 4 | disabled |
| multi-island | 4 | elite move checks every B/4; only pre-stop moves count as exposure |

Every cell has exactly B real attempts and B/8 attempts per agent.  The
durable controller records candidate hashes, parent hashes, visible rankings,
mutation coordinates, admission recovery, and local sequence numbers.  The
auditor rejects malformed candidates, schedule drift, quota imbalance,
non-real attempts, visibility/checkout races, heartbeat interventions,
missing causal migration exposure, and sandbox isolation violations.

## Prospective budget ladder

The earlier ordinary-LeadingOnes B=256 smoke and interrupted B=1,024 launch are
retained with `experiment-invalid.json` markers for provenance only.  The
public coordinate order made that task adaptively solvable in O(N) accepted
improvements, so neither its integrity pass nor its topology scores are
evidence.  No result from either launch enters the replacement analysis.

The prospective Permuted-LeadingOnes/NK phase ladder restarts at B=256 and
B=1,024 as engineering smokes, followed by a fresh confirmatory ladder at
B=4,096/8,192/16,384 with eight paired held-out seeds at every budget. Every
completed replacement cell remains reported, but the earlier single-seed
engineering-smoke directories are never upgraded into confirmatory replicates.

The confirmatory mechanism threshold is the earliest registered budget at
which eight paired held-out seeds pass all integrity gates and both paired contrasts
`multi-global` and `multi-partition` have positive landscape-bootstrap lower
bounds on Rugged, while hard-Smooth remains unsolved and its `multi-global`
upper bound is below zero. Final best is primary; best-so-far AUC, diversity,
active lineages, migration exposure, and recovery counts are secondary.
Effects from the two landscape families are never pooled.
Because the analysis searches three registered budgets for the earliest pass,
the formal directional gates use per-budget one-sided alpha 0.05/3 bootstrap
bounds. Ordinary 95% intervals remain descriptive; they cannot trigger the
threshold rule.
The Rugged decision also retains the calibration's practical floors within
the NK family: mean `multi-global` must be at least 0.25 held-out random SD and
mean `multi-partition` at least 0.10 held-out random SD. Each paired seed uses
its own frozen NK random SD; these standardized effects are never pooled with
or subtracted from Permuted LeadingOnes.

## What remains after a positive scripted threshold

A positive result would establish only topology-mechanism sensitivity under a
fixed high-diffusion policy.  The separately registered natural-agent arm uses
the same K=64/B=16,384 anchor, paired held-out seeds, quotas, topology, and
migration cadence, while removing the scripted parent-selection and mutation
schedule.  Its primary decision still requires Rugged multi-island to beat
both global visibility and permanent partition with positive paired-bootstrap
lower bounds.  The auditor additionally requires model-API-only networking,
the frozen first candidate, endogenous transition traces, runtime isolation,
and a migrant's later real submission in each exposed destination.

Even a positive natural-agent result is not the institutions conclusion.  The
claim still requires structured real tasks. Circle Packing and the certified
modular task are kept separate; neither may be pooled with
NK/Permuted LeadingOnes to manufacture a single favorable headline.
