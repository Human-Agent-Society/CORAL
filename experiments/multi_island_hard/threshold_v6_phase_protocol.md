# Preregistered v6 hardness-response phase map

## Purpose

This experiment asks where a frozen multi-island social-learning mechanism
helps as problem difficulty changes. It does **not** use a single favorable
Smooth/Rugged pair as the conclusion, and it does not treat simulator output
as evidence about natural agents or real software work.

The phase map is frozen before its held-out seeds are evaluated. Its seeds are
deterministically generated from the `threshold-v6-phase-heldout` namespace
and must have zero overlap with v4 calibration seeds or v5 CORAL seeds.

## Registered grid

- Eight agents with full visible-champion imitation.
- Mutation: 90% one-bit, 8% two-bit, 2% four-bit.
- Conditions: one global island; four permanent two-agent partitions; four
  two-agent islands with move-not-copy elite rotations at `B/4`, `B/2`, and
  `3B/4`.
- Twenty-four independent paired landscape-policy blocks.
- Budgets: 2,048; 4,096; 8,192; 16,384; 32,768 real proposals.
- Smooth: hidden-target, hidden-order Permuted LeadingOnes with
  `N = 128, 256, 512, 1,024, 2,048`.
- Rugged: adjacent hidden-seed NK with `N=512` and
  `K = 8, 16, 32, 64, 128`.
- Each Rugged block/K pair has a 256-sample random-reference SD computed from
  a separate deterministic RNG stream.

Initial candidates, landscape seeds, policy seeds, agent quotas, and mutation
draws are paired across topology conditions. Smooth and Rugged scores are
never pooled or subtracted because their null scales are incommensurate.

## Confirmatory decisions

Every Rugged `(K, B)` cell reports `multi-global` and `multi-partition` paired
effects, standardized only by that NK instance's random-reference SD. A cell
passes when both of these are true:

1. multi-global mean is at least 0.25 random SD and its multiplicity-controlled
   lower bound is positive;
2. multi-partition mean is at least 0.10 random SD and its
   multiplicity-controlled lower bound is positive.

The familywise alpha is 0.05. It is divided by all registered Rugged cells and
both contrasts. The analysis reports the full pass/fail surface and the first
passing budget within each K; it does not assume that benefit is monotone in K.
All confirmatory percentile bounds use 100,000 deterministic paired-bootstrap
draws so the most stringent registered tail contains approximately 100 draws.

For each Smooth `(N, B)` cell, the analysis reports exact-solution counts,
prefix progress, and `global-multi` prefix differences. Its one-sided bounds
divide alpha across all Smooth cells. `N>=512` is the preregistered hard-Smooth
region. The negative control tests whether increasing path length alone causes
an island advantage; a difficult Smooth task is not relabeled Rugged after the
results are seen.

A phase region is observed only if at least one Rugged cell passes and at
least one does not. This is a mechanism result, not an institutions result.

## Evidence ladder

1. This held-out simulator phase map locates a difficulty-response region.
2. The audited CORAL v5 budget ladder checks selected K=64 anchors through
   real worktrees, admission, grading, isolation, and migration.
3. The separately registered natural-agent arm tests whether the mechanism
   survives removal of the scripted mutation/controller policy.
4. Circle Packing and other structured real tasks test external validity.

Failure at a later level cannot be rescued by a positive earlier level.
