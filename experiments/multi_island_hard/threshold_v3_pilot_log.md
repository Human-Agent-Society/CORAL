# Threshold-v3 real-agent pilot log

This log records operational pilots separately from the registered eight-seed
matrix.  A one-seed pilot may validate plumbing or falsify an implementation
assumption; it cannot establish a topology effect.

## Smooth high-diffusion, B=256, held-out seed 1

The matched cells finished on 2026-07-25:

```text
global:       budget-256/smooth256_rep_v3/global_8/rep-01-retry-01
multi-island: budget-256/smooth256_rep_v3/multi_island_4/rep-01
```

The original `global_8/rep-01` stopped after two evaluations during an API
failure.  It remains on disk and the analyzer records it under
`superseded_invalid_runs`; the completed retry is the accepted logical cell.

Both accepted cells passed the fixed-budget integrity gates: 256 numeric real
attempts, eight agents with exactly 32 attempts each, the registered seed and
initial candidates, and `max_real_attempts` auto-stop.  The multi-island cell
also contains one rejected `--tune` request.  It returned no score, did not
advance the real budget, and contains the grader's tune-disabled marker, so it
is compliance evidence rather than a free-feedback violation.

### Matched outcome

| metric | global | four islands + migration | difference (multi - global) |
| --- | ---: | ---: | ---: |
| final best fitness | 0.630772 | 0.538916 | -0.091856 |
| random-baseline z | 11.178 | 3.882 | -7.296 |
| normalized best-so-far AUC | 0.457 | 0.218 | -0.240 |
| final candidate diversity | 0.128 | 0.317 | +0.189 |
| final inferred lineages | 1 | 4 | +3 |
| mean active inferred lineages | 2.609 | 5.445 | +2.836 |
| inferred cross-agent adoption | 0.258 | 0.105 | -0.153 |

The manipulation had the intended structural direction: the global pool
collapsed to one inferred lineage while four island lineages survived.  On
this additive Smooth task, preserving those lineages had a large score cost.
That is the registered negative-control pattern, not evidence for or against
the Rugged threshold.

The adoption-rate gate is miscalibrated for the real traces.  Agents explicitly
reused island-visible champions, but the conservative nearest-parent inference
reports only 0.258 in global, below the registered 0.50 gate, even though the
same trace ends in one lineage.  This gate is not silently changed after seeing
the result.  Later protocols must either validate a direct provenance marker
or register a lineage-collapse manipulation check before confirmation.

### Realized migration and runtime differences

The multi-island cell recorded twelve arrivals: four balanced round-robin
moves in each of three cycles.  Because the manager schedules from realized
polling ticks, the cycles occurred after approximately 68, 135, and 199 real
attempts rather than the simulator's exact 64, 128, and 192 boundaries.
Migration also restarted migrants and sandbox-affected bystanders; global has
no matched restart.  Generic heartbeat sessions produced long synthesis work
that the operator-side simulator does not model.  These timing and restart
differences must remain explicit confounds in any real-agent interpretation.

Wall-clock time was about 65 minutes for the accepted global retry and 38
minutes for multi-island.  This is not a throughput contrast: the cells ran
sequentially under visibly different API reliability periods.

## Decision

Do not expand the N=256 LLM matrix from this Smooth pilot.  Operator-side
out-of-selection falsification already shows that the K=32 advantage depends
on local mutation and does not identify elite migration over permanent
partition.  The next model-budget gate is the certified-composition temporal
bracket, followed by a separate real structured task.  NK remains a conditional
mechanism probe, not confirmatory evidence for the blog's general claim.
