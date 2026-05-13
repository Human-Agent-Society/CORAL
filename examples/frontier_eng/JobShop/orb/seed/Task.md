# Task: Solve and Evaluate ORB (Applegate & Cook, 1991) JSSP Instances

## Audience and assumptions

This task assumes you have general CS background but little/no prior scheduling knowledge.

## Problem background

A Job Shop Scheduling Problem (JSSP) instance contains:

- **Jobs**: each job is a sequence of operations.
- **Machines**: each operation must run on one machine.
- **Processing times**: each operation has a fixed duration.
- **Precedence constraints**: in one job, operation `k+1` cannot start before operation `k` finishes.
- **Machine constraints**: a machine can run at most one operation at a time.

Goal: minimize **makespan** (finish time of the last completed operation).

## Family instances covered in this task

- Prefix: `orb`
- Instances: orb01-orb10
- Size range: 10x10
- Breakdown: orb01-orb10 are all 10x10.

## Input / output specification

### Input (conceptual)

Each run receives one benchmark instance containing:

- `duration_matrix[j][k]`: processing time of operation `k` in job `j`
- `machines_matrix[j][k]`: machine used by operation `k` in job `j`
- metadata (`optimum`, `lower_bound`, `upper_bound`, `reference`)

### Output (conceptual)

A feasible schedule:

- start time for every operation
- implied machine timelines and job completion times
- scalar objective: `makespan`

In this workspace:

- baseline returns a pure-python result dict with `makespan`.
- reference returns a `Schedule` from `job_shop_lib`.

## Expected result quality

- If `optimum` is known: ideally reach optimum.
- If `optimum` is unknown: get as close as possible to best-known feasible (`upper_bound`) and theoretical limit (`lower_bound`).
- Baseline is expected to be valid but not necessarily near-optimal on large instances.

## Scoring used by `verification/evaluate.py`

For each instance and solver result `C` (makespan):

1. Best-known score:
   - `target = optimum` (if known) else `upper_bound`
   - `score_best = min(100, 100 * target / C)`
2. Theoretical-limit score:
   - `score_lb = min(100, 100 * lower_bound / C)`

Interpretation:

- Higher is better.
- `100` means matching target (or lower bound under `score_lb`).
- The script reports per-instance scores and averaged family scores.

## Implementations in this folder

- `baseline/init.py`:
  - Greedy `EST + SPT` list scheduling.
  - Pure Python, standard library only.
  - No `job_shop_lib` dependency.
- `verification/reference.py`:
  - OR-Tools CP-SAT reference (allowed external algorithm).
- `verification/evaluate.py`:
  - Runs baseline and reference on the same set.
  - Reports makespan, runtime, best-known score, lower-bound score.
  - Shows comparison against theoretical score ceiling (100 under `score_lb`).

## How to run

```bash
python JobShop/orb/verification/evaluate.py --max-instances 3 --reference-time-limit 5
python JobShop/orb/verification/evaluate.py --instances orb01 orb02 --reference-time-limit 10
```
