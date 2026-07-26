# Preregistered v6 extreme-hardness extension

## Purpose

The original v6 phase map reaches adjacent-NK `K/N = 128/512 = 0.25`.
Its registered construct audit confirms a real gradient, but the hardest end
still has mean one-bit autocorrelation near `0.75`. This independent held-out
extension tests substantially harder Smooth paths and Rugged landscapes whose
one-bit neighbourhoods approach the random-energy limit.

The initial 24-block extension was frozen and its topology-free construct
audit passed, but an outcome-free sensitivity audit performed while both
topology raw files were absent showed only 33.9% approximate power for a
`+0.25` effect when paired-block SD is `0.5`. That version is superseded before
any extreme topology outcome is evaluated. The confirmatory v2 design below
uses 64 fresh paired blocks, giving approximately 87.2% power in that scenario.

Because this run is materially longer than the original map, the formal
operator uses a source-bound resumable wrapper. It atomically checkpoints every
24 completed condition runs and rejects any configuration, seed hash, policy
hash, item key, or result shape that does not match the registered run. The
checkpoint may be inspected only for completed/expected counts until the full
map finishes; interim topology outcomes must not be analyzed or reported.

Changing Rugged `N` is a computational device that makes extreme `K/N`
feasible. The extension uses `N=128`, still a search space of size `2^128`,
and treats affected fraction `(K+1)/N` and empirically measured one-bit
autocorrelation as the difficulty coordinates. Its `K=32` cell bridges the
original v6 boundary because `33/128` is within `0.01` of `129/512`. Scores
are never pooled across the two experiments or across landscapes.

## Registered grid

- Eight agents with full visible-champion imitation.
- Mutation: 90% one-bit, 8% two-bit, 2% four-bit.
- Conditions: one global island; four permanent two-agent partitions; and
  four two-agent islands with move-not-copy elite rotations at `B/4`, `B/2`,
  and `3B/4`.
- Sixty-four fresh paired landscape-policy blocks with zero seed overlap
  against v4, v5, or the original v6 map.
- Budgets: 16,384; 32,768; 65,536 real proposals.
- Smooth negative control: hidden-target, hidden-order Permuted LeadingOnes
  with `N = 2,048, 4,096, 8,192`.
- Rugged: adjacent hidden-seed NK with `N=128` and
  `K = 32, 64, 96, 120`, corresponding to affected fractions
  `0.258, 0.508, 0.758, 0.945`.
- Each Rugged block/K pair has a 512-sample random-reference mean and SD from a
  separate deterministic RNG stream.

Initial candidates, landscapes, policy RNGs, quotas, and mutation draws are
paired across topology conditions. The compact Smooth implementation stores
the mismatch set in hidden-order coordinates; it is score-equivalent to the
literal bit-string implementation and changes no search rule.

## Construct-validity gate

Before topology results may be interpreted, a topology-free audit samples 256
random point/one-bit-neighbour pairs for every block and K. The construct gate
requires all of the following:

1. every Smooth cell has `B/N² <= 0.02`;
2. mean Rugged one-bit autocorrelation strictly decreases at every K;
3. at least 54 of 64 blocks have lower autocorrelation at K=120 than K=32;
4. mean K=32 minus K=120 autocorrelation is at least 0.55;
5. mean K=120 autocorrelation is at most 0.15; and
6. the K=32 affected fraction is within 0.01 of the original v6 boundary.

Failure invalidates the nominal extreme-hardness interpretation and cannot be
rescued using topology outcomes.

## Confirmatory topology decisions

Every Rugged `(K, B)` cell reports paired `multi-global` and
`multi-partition` effects in its own landscape's random-reference SD units.
Familywise alpha 0.05 is divided across all 12 cells and both contrasts. A
cell passes only when all three gates hold:

1. multi-global mean is at least 0.25 random SD and its controlled lower
   bound is positive;
2. multi-partition mean is at least 0.10 random SD and its controlled lower
   bound is positive; and
3. every topology's mean final score exceeds the equal-budget iid-random-search
   expected maximum, approximated in random-SD units by Blom's normal-order
   statistic, plus a preregistered 0.25 SD practical margin.

The third gate prevents a super-hard cell in which all methods merely take the
best of many lottery tickets from being labelled an island advantage. The
normal approximation is appropriate to an NK score averaged over 128 bounded
components and is used only as a conservative progress floor, never as the
effect scale. All controlled bounds use 100,000 deterministic paired-bootstrap
draws. The analysis reports the whole surface; non-monotonicity is allowed.

Smooth is a negative control. For every `(N, B)` cell the analysis reports
prefix progress, exact solutions, and the paired `global-multi` prefix
difference with familywise-controlled bounds. Hardness alone is not relabelled
as ruggedness after outcomes are seen.

## Claim boundary and execution order

This extension will be launched after the already-running original v6 map and
the v5 `B=4096` CORAL block finish, so it cannot silently change those runs or
compete with their fixed compute allocation. It is an out-of-range scripted
mechanism test, not evidence that institutions help natural agents. A positive
result still requires the audited CORAL anchor, natural-agent arm, and Circle
Packing external validation. A negative result cannot be hidden by reporting
only a favourable original-v6 cell.
