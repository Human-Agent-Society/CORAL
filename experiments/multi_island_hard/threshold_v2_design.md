# Held-out N=128 boundary/diversity threshold study

## Question and interpretation boundary

The certified modular v8 study is a positive control for carrying verified
components. This free-allocation study asks a different question:

> As feedback budget and island count increase, do boundaries plus selective
> migration outperform one globally visible population specifically on a
> rugged landscape?

The primary contrast is paired `multi_island_4 - global_8`. The matched
`multi_island_4 - partition_4` contrast asks whether migration adds value beyond
boundaries, and `multi_island_2 - global_8` is an island-count dose diagnostic.
No agent is assigned a coordinate range, module, or privileged basin.

## Falsification-first calibration

Making NK larger is not by itself a sensitivity argument. Before selecting the
LLM confirmation task, `calibrate_threshold_v2_topologies.py` ran a conventional
two-point-crossover tournament GA on eight calibration seeds across
`K=0/4/8/12/16/24` and the full budget ladder. No K/budget cell passed its
predeclared island-sensitivity gate. NK is therefore not claimed to
unconditionally favor islands.

`calibrate_threshold_v2_takeover.py` tests the narrower mechanism asserted in
the blog: everyone who sees the same attempt pool adopts its current champion.
It compares one, two, and four visible populations. This is a
mechanism-positive calibration, not an LLM forecast. Real runs report
diversity, duplicate rates, and island-count dose without conditioning
inclusion on whether takeover occurred. If globally visible agents do not
collapse onto one lineage, the proposed mechanism is falsified even when a
score contrast happens to be positive.

The eight seeds used during task calibration are frozen in
`threshold_v2_calibration_landscapes.json` and excluded from every LLM cell.
The paired confirmation seeds were sampled only after that exploratory task
selection and live solely in the two private task bundles.

## Held-out tasks, topology dose, and budgets

Both confirmation tasks use literal 128-bit candidates and the same adjacent
NK grader:

| task | K | role |
| --- | ---: | --- |
| `smooth128_rep_v2` | 0 | unique-optimum coordination control |
| `rugged128_k12_rep_v2` | 12 | held-out many-basin diversity stress test |

The takeover calibration selects the earliest passing budget and then the
smallest K in a tie. That frozen rule selected K=12 at 2,048 evaluations (K=16
also first passed there; K=8 first passed at 4,096). K=12 is deliberately
medium-rugged rather than maximally random: very high K can erase the local
signal that either topology needs to improve. Registered
budgets are 128, 256, 512, 1,024, 2,048, and 4,096 real evaluations. Every
condition uses the same eight agents and an atomic `budget / 8` quota per
agent. Migration cadence is `budget / 4`, clipped to 64–512 evaluations.

The topology conditions are:

| condition | islands × residents | migration |
| --- | --- | --- |
| `global_8` | 1 × 8 | off |
| `partition_4` | 4 × 2 | off |
| `multi_island_2` | 2 × 4 | round-robin, at most 2 movers/cycle |
| `multi_island_4` | 4 × 2 | round-robin, at most 4 movers/cycle |

Each base agent's first candidate is deterministically derived from its id and
is identical across paired topology cells. The eight starts are distinct.
Subsequent allocation is free. The sandbox allowlists only
`api.appintheloop.com`, which is required by the model runtime; source hosts
such as GitHub remain blocked so a pushed private bundle cannot be downloaded.

## Outcomes and registered decision rule

`diagnose_threshold_v2.py` freezes a random-candidate mean/SD and a 64-start
greedy reference for each held-out task/seed. The K=0 reference is verified
exact; the K=12 reference is explicitly approximate and is secondary only.

Primary performance is final random-baseline z-score:

```text
random_z = (best_score - random_mean) / random_sd
```

Secondary outcomes are raw best score, reference gain, best-so-far AUC,
midpoint/final Hamming diversity, unique and duplicate candidates, migration
chronology, and quota balance.

The earliest full multi-island threshold is the first budget where all eight
held-out seed pairs pass integrity gates and:

1. Rugged `multi_island_4 - global_8` is at least 0.50 random-candidate SD with
   a paired bootstrap 95% lower bound above zero;
2. `(multi_island_4 - global_8 on Rugged) - (the same on Smooth)` is at least
   0.50 SD with its paired lower bound above zero; and
3. Rugged `multi_island_4 - partition_4` is positive with its paired lower
   bound above zero, showing that realized migration added value beyond four
   isolated populations.

`multi_island_2` is reported as a predeclared dose comparison but is not used
to replace an unfavorable primary result. If no budget passes, the result is a
registered null for this model, policy, and task family—not evidence that
islands never help.

## Staging and integrity

Launches are staged to avoid spending the 4,096-query cells before mechanics
work: first one held-out seed at 1,024 and 2,048 across all conditions, then the
remaining registered cells. Pilot cells remain labeled operational and cannot
satisfy the eight-seed decision rule.

Every accepted cell needs the exact budget, eight equal per-agent quotas,
numeric feedback, the matching private seed and seed index, registered
topology/cadence/heartbeat, topology-invariant first candidates, an allowlist
containing exactly the model API domain, no grader errors, no migration notes
in controls, and a real migration event in enabled conditions. At most one malformed candidate is
allowed and remains charged as numeric zero.

A positive threshold supports a controlled black-box diversity-and-transfer
claim. It does not prove semantic institutions or general superiority; those
still require real modular tasks and independent replication.
