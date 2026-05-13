# Fiber F1 Specification: WDM Channel + Power Allocation

## Background

In a WDM (Wavelength Division Multiplexing) optical system, multiple users share the same fiber by occupying different wavelength channels.

For each user, you must decide:

- which channel to use (discrete decision),
- how much launch power to put on channels (continuous decision).

More power can improve signal quality, but channels interfere with each other (especially nearby channels), and total power is limited.

From a CS perspective, this is a constrained optimization problem combining:

- matching/assignment (`user -> channel`),
- continuous resource allocation (power),
- non-linear quality effects (BER/SNR).

## What You Need To Do

Implement one function in the candidate solver:

- file to edit: `baseline/init.py`
- function to evolve: `allocate_wdm(...)`

Everything under `verification/` is read-only for benchmarking.

## Function Interface

```python
def allocate_wdm(
    user_demands_gbps,
    channel_centers_hz,
    total_power_dbm,
    pmin_dbm=-8.0,
    pmax_dbm=3.0,
    target_ber=1e-3,
    seed=0,
):
    return {
        "assignment": np.ndarray,  # shape (U,), int, channel index or -1
        "power_dbm": np.ndarray,   # shape (C,), float, per-channel power
    }
```



Inputs:

- `user_demands_gbps` (`U` users): throughput demand per user.
- `channel_centers_hz` (`C` channels): fixed channel frequencies.
- `total_power_dbm`: global power budget. Important: verification checks this in linear power domain (`mW`), not by direct dBm sum.
- `pmin_dbm`, `pmax_dbm`: per-channel power limits.
- `target_ber`: BER threshold for pass/fail counting.

Outputs:

- `assignment[u]`:
  - `-1` means user `u` is not served,
  - `0..C-1` means assigned channel index.
- `power_dbm[ch]`: launch power for each channel.

## Hard Validity Constraints

Your output must satisfy all of the following:

1. `assignment.shape == (U,)`
2. `power_dbm.shape == (C,)`
3. every assignment value is in `[-1, C-1]`
4. no channel can be assigned to multiple users
5. all channel powers are within `[pmin_dbm, pmax_dbm]`
6. total linear power `sum(10^(p_dbm/10)) <= 10^(total_power_dbm/10)`

If this structural check fails, verification returns error immediately.

## Verification Pipeline and Metrics

`verification/run_validation.py` builds a fixed scenario (`seed=42`) and evaluates candidate/oracle with the same code path.

Scenario scale:

- users: `14`
- channels: `20`
- demands: uniform in `[180, 320]` Gbps

Evaluation model (proxy but engineering-motivated):

1. For each served user, compute signal and inter-channel interference.
2. Convert to `SNR`.
3. Convert SNR to BER using OptiCommPy `theoryBER` (QAM).
4. Convert SNR to capacity proxy.

Reported metrics:

- `demand_satisfaction`
- `ber_pass_ratio`
- `spectral_utilization`
- `avg_snr_db`

Composite score:

`0.35*satisfaction + 0.40*ber_pass + 0.05*utilization + 0.20*snr_term - 0.15*power_penalty`

Validity thresholds (metric-level):

- `demand_satisfaction >= 0.30`
- `ber_pass_ratio >= 0.20`
- `spectral_utilization >= 0.55`

## Baseline (Simple, Low Dependency)

`baseline/init.py` baseline logic:

1. assign users to channels by index order,
2. split active-channel power equally under global budget,
3. clip power to `[pmin_dbm, pmax_dbm]`.

This baseline is intentionally simple and only uses `numpy`.

## Oracle (Stronger Reference)

`verification/oracle.py` uses stronger search strategies:

- interference-aware initial assignment (spread channels),
- demand-aware channel mapping,
- demand-weighted initial power,
- local search over assignment and power,
- optional SciPy differential evolution for power refinement.

Oracle modes:

- `--oracle-mode heuristic`: deterministic/local-search only
- `--oracle-mode hybrid_scipy`: local-search + SciPy global refinement
- `--oracle-mode auto`: choose available stronger backend automatically

## Files in `verification/outputs/` and How to Read Them

After each run, two key files are generated:

- `summary.json`
- `task1_verification.png`

`summary.json` contains:

- `candidate`: full evaluated metrics for your solver
- `oracle`: same metrics for reference strategy
- `oracle_meta`: backend/mode details (useful for reproducibility)
- `score_gap_oracle_minus_candidate`: performance gap

`task1_verification.png` contains:

- left subplot: per-user demand vs achieved capacity (candidate vs oracle)
- right subplot: per-channel power profiles (candidate vs oracle)

These two artifacts are enough for leaderboard scoring and qualitative diagnosis.

## Why This Task Is Engineering-Relevant

This task mimics practical network control tradeoffs:

- serving more users vs preserving link reliability,
- using more power vs causing cross-channel interference,
- static allocation vs adaptive optimization.

A better policy can translate into better throughput-per-power and lower retransmission risk.
