# High-dimensional multi-island difficulty ladder

The latest preregistered extension is the
[`threshold_v6_phase_protocol.md`](threshold_v6_phase_protocol.md) hardness-response
map. It crosses five Smooth sizes, five Rugged epistasis levels, and five
budgets on 24 new paired blocks. The v6 simulator locates a phase region; it
does not replace the audited CORAL v5 anchor, natural-agent arm, or real-task
validation.

The original `N=20` Smooth/Rugged NK cells are retained as sanity checks. They
are not sufficient to establish a ruggedness threshold: `K=0` is separable,
`K=4` has many local optima but only 16 scalar queries are available, and each
condition used one frozen landscape seed.

This follow-up fixes the main design limitation with a pre-registered ladder:

| task | N | K | role |
| --- | ---: | ---: | --- |
| `smooth128` | 128 | 0 | high-dimensional separable control |
| `rugged128_k4` | 128 | 4 | moderate epistasis |
| `rugged128_k12` | 128 | 12 | strong epistasis |
| `rugged128_k24` | 128 | 24 | strongest ladder stress test |

Each task has global, partition, and multi-island conditions, three
operational repetitions, four `mafia/glm-5.2` OpenCode agents, and exactly 24
finalized real evaluations. Migration checks every six evaluations. The
hard-ladder-specific role seed explicitly names the 24-evaluation budget.

There is no exact oracle at `N=128`. `diagnose_landscapes.py` records a fixed
operator-side Monte Carlo and multi-start greedy reference, plus random
baseline moments. `analyze_hard.py` reports raw score, fraction of the declared
reference gain, random-z score, best-so-far AUC, diversity, migration
compliance, null-rate, and agent-runtime/API error counts. The reference is
approximate and is never called a global optimum.

Validate and inspect the matrix without launching agents:

```bash
uv run coral validate experiments/multi_island_hard/tasks/institutional_landscape
uv run python experiments/multi_island_hard/run_matrix.py --dry-run
```

Run and analyze:

```bash
uv run python experiments/multi_island_hard/run_matrix.py \
  --results-root /var/tmp/coral-institutions-results/hard-ladder-v1 \
  --max-parallel 2
uv run python experiments/multi_island_hard/analyze_hard.py \
  --results-root /var/tmp/coral-institutions-results/hard-ladder-v1
```

Results from the first launch that accidentally used the pilot 16-evaluation
role protocol are marked `experiment-invalid.json` and are not analyzed.
The next partial launch showed agents spending their search on false-positive
seed reconstruction from rounded scalar scores. It is also invalidated; the
final protocol states that the seed is an independently sampled 256-bit token
and treats the task as black-box search.

The manager's stop condition is audited rather than trusted: because agents
can submit concurrently, a run may finalize one extra real attempt before the
manager observes the stop threshold. Any cell whose finalized real count is
not exactly 24 is invalid for the ladder. The interrupted July 24 collection
was not used as a result set for this reason (one cell reached 25 real
attempts).

## Replicated threshold v2

The original ladder remains a one-seed stress test. The held-out replacement
uses `smooth128_rep_v2` and `rugged128_k12_rep_v2`, eight paired confirmation
seeds that are disjoint from task-calibration seeds, eight agents, equal
per-agent quotas, model-API-only networking, and budgets
128/256/512/1,024/2,048/4,096. It compares global search with two and four
islands plus a matched four-way no-migration partition. Verified component
transfer is tested separately by the modular v8 package.

Run `calibrate_threshold_v2_topologies.py` for the conventional-GA
falsification check and `calibrate_threshold_v2_takeover.py` for the narrower
champion-takeover sensitivity check. `diagnose_threshold_v2.py` reproduces the
held-out per-seed references, `run_threshold_v2.py --budget <registered
budget>` collects one isolated budget slice, and `analyze_threshold_v2.py`
computes paired-seed contrasts. See `threshold_v2_design.md` and
`threshold_v2_protocol.md` for the registered decision rule and participant
instructions.

## Social-learning threshold v3

Version 2 made the landscape and budget harder, but its first valid natural
Smooth/global pilot retained eight inferred candidate lineages and had zero
cross-agent parent adoption. It therefore did not activate the full champion
takeover assumed by the mechanism-positive calibration. See
`threshold_v2_pilot_log.md` for the audited behavior and liveness record.

Version 3 doubles the candidate dimension to N=256, uses K=0/K=32 held-out
tasks, and extends the budget ladder to 8,192. More importantly,
`calibrate_threshold_v3_social.py` maps imitation probability rather than
assuming it: p=0 is an executable exact topology null, while p=1 is an explicit
high-diffusion positive control. `run_threshold_v3.py --policy natural` and
`--policy high_diffusion` keep endogenous and manipulated behavior separate.
`analyze_threshold_v3.py` adds mutation-operator entropy, coordinate overlap,
cross-agent parent adoption, and active-lineage manipulation gates.

The offline boundary calibration selected K=32/B=4,096: under full diffusion,
four islands beat global by 0.547 random-baseline SD (bootstrap 95% interval
0.312 to 0.770), with a 0.610 SD rugged-minus-smooth interaction (0.379 to
0.837). No p=0.75 cell passed, so the calibrated claim is conditional on high
social learning rather than a universal island advantage. See
`threshold_v3_design.md` for staging and interpretation.  The fresh-seed
operator audit narrows it further: fixed four-bit mutation reverses the
island/global effect, and elite migration is not separated from fixed or worst
migration relative to permanent partition.

The first matched real-agent Smooth/high-diffusion pilot is recorded in
`threshold_v3_pilot_log.md`.  Global collapsed to one inferred lineage and
outperformed four islands by 0.092 raw fitness; four islands retained four
lineages and substantially more candidate diversity.  The result validates
the negative-control direction for one seed, while also exposing a conservative
adoption metric and realized migration-tick drift.  It is not expanded into a
large LLM matrix because the operator audit already prevents a broad NK claim.

## Operator-robust scale threshold v4

Version 4 doubles dimension again to N=512 and screens K=0/16/32/64/128 at
4,096/8,192/16,384 evaluations.  It does not treat a larger K as automatically
harder or favorable: one-bit, two mostly-local mutation mixtures, and fixed
four-bit mutation are crossed explicitly on eight calibration landscapes.
The decision file reports a boundary threshold (`multi_island_4-global_8` plus
the Rugged-minus-Smooth interaction) separately from a migration threshold
(`multi_island_4-partition_4`).

`calibrate_threshold_v4_scale.py` must finish its complete registered grid
before any participant launch. `run_threshold_v4.py` reads that result and
refuses reduced calibrations, unselected K values, or a different budget.
The future participant seeds and all candidate K bundles are already frozen
and disjoint from calibration. `diagnose_threshold_v4.py` generates held-out
references only for the selected pair; `analyze_threshold_v4.py` additionally
requires every last migrant to submit another real attempt and replaces the
miscalibrated v3 adoption-rate gate with directly observed global lineage
collapse plus active-lineage separation. See `threshold_v4_design.md` for the
full staged rule and interpretation boundary.

Before launching the first selected cell, run
`python experiments/multi_island/sandbox_canary.py`. It executes a real
sandboxed `coral eval --no-wait` and fails unless foreign island state and
foreign-island worktrees are both unreadable and unwritable, the attempt lands
only in the current island, and the fixed-budget lock is island-scoped. Canary
directories are retained under `/var/tmp` for audit.

The complete calibration selected K=32/B=8,192 for the boundary pilot and
K=64/B=16,384 as the first operator-side migration threshold. Fixed four-bit
mutation passed neither generalization gate. The selected held-out landscapes
also pass the frozen random/autocorrelation/local-maxima diagnostics. See
`threshold_v4_calibration_log.md` for effect sizes, file hashes, and the narrow
interpretation; no participant result has yet been used to alter selection.

## Non-saturating hard Smooth control v5

Version 5 addresses the remaining K=0 saturation problem with a second Smooth
family: hidden-target, hidden-coordinate-order Permuted LeadingOnes at N=512.
It has one strict one-bit local optimum, but the registered blind local policy
solves at most 91/512 prefix bits at B=16,384 across the complete calibration.
Random-z effects are never subtracted across Permuted LeadingOnes and NK; the
original within-NK ruggedness interaction remains the comparable gate, and
Permuted LeadingOnes is a separate directional negative control.

`calibrate_threshold_v5_hard_smooth.py` selects K=64/B=16,384 as the first
hard anchor passing boundary, migration, within-NK interaction, hard-Smooth
direction, and non-saturation gates across one-bit and both registered local
mixtures. `run_threshold_v5_mechanism.py` executes the held-out scripted arm
through real CORAL worktrees and migration. `audit_threshold_v5_mechanism.py`
must pass before `analyze_threshold_v5_mechanism.py` reads performance.
`diagnose_threshold_v5.py` separately freezes properties of the actual eight
held-out landscapes: paired seeds, the exact unique one-bit optimum of Smooth,
NK random/neighbor moments, and at least 24 distinct Rugged maxima among 32
deterministic greedy starts per seed. The confirmatory analyzer also requires
the held-out hard-Smooth control to remain unsolved and global visibility to
beat multi-island; a Rugged-only positive result is insufficient.

The ordinary-LeadingOnes B=256 smoke and interrupted B=1,024 launch are both
marked invalid because their public coordinate order creates an O(N) adaptive
shortcut. They are retained for provenance and cannot be used even as negative
evidence. The replacement one-seed phase ladder restarts with Permuted
LeadingOnes at B=256/1,024 for engineering only. Fresh direct result slices at
B=4,096/8,192/16,384 form the confirmatory ladder, with eight paired held-out
seeds at every budget; the earlier single-seed smoke directories cannot be
promoted into that matrix. Even a supported threshold is not natural-agent or
institutions evidence. See `threshold_v5_design.md` and
`threshold_v5_calibration_log.md`.
After each slice passes `audit_threshold_v5_mechanism.py` and is analyzed,
`summarize_threshold_v5_ladder.py` refuses an incomplete matrix and reports the
earliest budget satisfying the full Rugged plus hard-Smooth rule.

The separately registered natural-agent follow-up uses
`run_threshold_v5_natural.py` and `threshold_v5_natural_protocol.md` at the
same K=64/B=16,384 anchor and the same eight held-out seeds. It removes the
scripted parent-selection and mutation schedule; search operators, copying,
and coordination are endogenous outcomes. Run it only after the scripted arm
passes its integrity gate. `audit_threshold_v5_natural.py` requires balanced
per-agent quotas, the frozen first candidate, model-API-only networking,
runtime isolation, and a migrant's later real submission in every exposed
destination. `analyze_threshold_v5_natural.py` keeps the two task families
separate and requires positive paired lower bounds against both global and
permanent partition on Rugged. A positive natural arm still needs a
structured real-task replication.
