# Fiber F2 Specification: Joint MCS + Power Scheduling

## Background

In digital communication, each user link can choose a modulation level (MCS) and transmit power.

- Higher MCS gives higher throughput but usually requires better SNR.
- Higher power improves SNR but consumes shared budget.

This is a classic cross-layer tradeoff between throughput and reliability under a global resource limit.

From a CS perspective, this can be seen as a multiple-choice knapsack style problem:

- each user must pick exactly one `(MCS, power)` option,
- all users share one global power budget,
- objective mixes satisfaction, reliability, and spectral efficiency.

## What You Need To Do

Implement the candidate policy function:

- editable file: `baseline/init.py`
- function to evolve: `select_mcs_power(...)`

Verification logic and oracle remain read-only.

## Function Interface

```python
def select_mcs_power(
    user_demands_gbps,
    channel_quality_db,
    total_power_dbm,
    mcs_candidates=(4, 16, 64),
    pmin_dbm=-8.0,
    pmax_dbm=4.0,
    target_ber=1e-3,
    seed=0,
):
    return {
        "mcs": np.ndarray,       # shape (U,), each value must be in mcs_candidates
        "power_dbm": np.ndarray, # shape (U,)
    }
```



Inputs:

- `user_demands_gbps`: required throughput per user.
- `channel_quality_db`: per-user channel quality estimate (SNR-like).
- `total_power_dbm`: global power budget over all users.
- `mcs_candidates`: allowed modulation orders, default `(4, 16, 64)`.
- `pmin_dbm`, `pmax_dbm`: per-user power bounds.
- `target_ber`: BER pass threshold.

Outputs:

- `mcs[u]`: modulation order selected for user `u`.
- `power_dbm[u]`: allocated power for user `u`.

## Hard Validity Constraints

1. output must be dict with keys `mcs`, `power_dbm`
2. `mcs.shape == (U,)`
3. `power_dbm.shape == (U,)`
4. each `mcs[u]` must belong to `mcs_candidates`
5. each power within `[pmin_dbm, pmax_dbm]`
6. total linear power must not exceed budget

If hard checks fail, run stops with error summary.

## Verification Pipeline and Metrics

Scenario (`seed=123`) in verification:

- users: `22`
- demand: uniform in `[110, 280]` Gbps
- quality: uniform in `[12, 21]` dB
- power budget: `9 dBm`
- BER target: `7e-4`

For each user:

1. `snr_db = channel_quality_db + power_dbm`
2. BER from OptiCommPy `theoryBER(M, EbN0)`
3. throughput proxy from `log2(M)` and BER-dependent reliability

Metrics:

- `demand_satisfaction`
- `ber_pass_ratio`
- `avg_bits_per_symbol` (spectral efficiency proxy)

Score:

`0.45*satisfaction + 0.40*ber_pass + 0.15*se_term`

Validity thresholds:

- `demand_satisfaction >= 0.40`
- `ber_pass_ratio >= 0.03`

## Baseline (Simple, Low Dependency)

Current baseline in `baseline/init.py`:

1. quality-threshold MCS selection (`>=15 -> 16`, `>=22 -> 64`, else lowest),
2. equal power split across users,
3. clip powers to valid range.

Dependency is only `numpy`.

## Oracle (Stronger Reference)

`verification/oracle.py` provides stronger optimization:

- discretize candidate powers (0.5 dB step),
- enumerate per-user options `(MCS, power)`,
- optimize combined utility with global budget.

Backends:

- CP-SAT exact solve (`ortools`) on the discretized model,
- deterministic DP fallback if CP-SAT unavailable.

Oracle modes:

- `--oracle-mode exact`: prefer CP-SAT
- `--oracle-mode heuristic`: force DP fallback
- `--oracle-mode auto`: CP-SAT first, DP fallback

## Files in `verification/outputs/`

Generated per run:

- `summary.json`
- `task2_verification.png`

`summary.json`:

- `candidate`: your policy's evaluated metrics and raw vectors
- `oracle`: reference metrics and vectors
- `oracle_meta`: which backend solved oracle
- `score_gap_oracle_minus_candidate`: score difference

`task2_verification.png`:

- left: quality vs selected MCS scatter (candidate vs oracle)
- right: per-user achieved throughput bars (candidate vs oracle)

These outputs help both automatic ranking and manual diagnosis.

## Why This Task Is Engineering-Relevant

This task mirrors real adaptive-link control:

- aggressive modulation can improve rate but may break BER,
- conservative modulation is reliable but under-utilizes spectrum,
- power sharing among users introduces coupling.

Better policies can increase effective throughput under the same energy budget.
