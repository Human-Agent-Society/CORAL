# Fiber F3 Specification: DSP Mode Scheduling (EDC vs DBP)

## Background

In coherent optical receivers, there are different DSP processing modes:

- `EDC`: lower compute/latency, weaker compensation.
- `DBP`: stronger compensation, higher latency cost.

So for each user, enabling DBP may improve BER, but if too many users use DBP, total latency can violate system budget.

From a CS perspective, this is a constrained binary optimization:

- choose mode `0/1` per user,
- maximize weighted communication utility,
- satisfy global latency constraint (and optional DBP count cap).

## What You Need To Do

Implement one candidate function:

- editable file: `baseline/init.py`
- function to evolve: `choose_dsp_mode(...)`

Verification scripts and oracle are read-only.

## Function Interface

```python
def choose_dsp_mode(user_features, latency_budget_s, max_dbp_users=None, seed=0):
    return {"mode": np.ndarray}  # shape (U,), values in {0,1}
```

Mode convention:

- `0` = EDC
- `1` = DBP



`user_features` contains per-user arrays:

- `est_snr_db`: baseline SNR estimate before DBP gain
- `traffic_weight`: user importance weight
- `dbp_gain_db`: expected SNR gain when mode is DBP
- `edc_latency_s`: per-user latency in EDC
- `dbp_latency_s`: per-user latency in DBP
- `modulation_order`: BER model parameter
- `target_ber`: BER pass threshold

Other inputs:

- `latency_budget_s`: global total latency budget
- `max_dbp_users`: optional cap for number of DBP users

Output:

- `mode[u] in {0,1}` for each user.

## Hard Validity Constraints

1. output is dict with key `mode`
2. `mode.shape == (U,)`
3. each value in `{0,1}`

Then metric-level validity requires:

- total latency within budget tolerance
- BER pass ratio above threshold

## Verification Pipeline and Metrics

Scenario (`seed=7`) is intentionally difficult and structured:

- Group A: very low SNR, low traffic weight, high DBP latency cost
- Group B: moderate SNR, very high traffic weight, high DBP gain, low DBP latency cost
- Group C: high SNR users where DBP has lower marginal value

Scale:

- users: `24`
- `max_dbp_users`: `7`

Evaluation:

1. effective SNR = `est_snr_db + mode * dbp_gain_db`
2. BER from OptiCommPy `theoryBER`
3. reliability-adjusted utility weighted by `traffic_weight`
4. latency from selected mode per user

Metrics:

- `weighted_utility`
- `ber_pass_ratio`
- `dbp_ratio`
- `latency_overflow`

Score:

`0.65*weighted_utility + 0.30*ber_pass + 0.05*(1-dbp_ratio) - 0.70*latency_overflow`

Validity thresholds:

- `latency <= budget * 1.001`
- `ber_pass_ratio >= 0.18`

## Baseline (Simple, Low Dependency)

`baseline/init.py` currently does:

1. sort users by lower SNR first,
2. greedily assign DBP while latency budget allows,
3. stop when budget (or optional DBP cap) is reached.

This is easy to understand but ignores weighted global tradeoffs.

## Oracle (Stronger Reference)

`verification/oracle.py` models this as knapsack-like optimization:

- per user, compute utility gain of DBP over EDC,
- extra DBP latency is item cost,
- solve via CP-SAT when `ortools` is available,
- fallback to deterministic DP otherwise,
- perform strict post-check cleanup to avoid latency overflow.

Oracle modes:

- `--oracle-mode exact`: attempt CP-SAT first
- `--oracle-mode heuristic`: force DP
- `--oracle-mode auto`: CP-SAT first, DP fallback

## Files in `verification/outputs/`

Generated artifacts:

- `summary.json`
- `task3_verification.png`

`summary.json` contains:

- `candidate`: your full metrics and vectors
- `oracle`: reference metrics and vectors
- `oracle_meta`: solver backend information
- `score_gap_oracle_minus_candidate`

`task3_verification.png` contains:

- left: user SNR profile + which users receive DBP in candidate/oracle
- right: total latency bars (candidate/oracle) with budget line

Use this to debug whether your policy is choosing DBP on the right users.

## Why This Task Is Engineering-Relevant

This task captures a realistic compute-vs-quality tradeoff:

- stronger DSP improves link quality,
- but DSP complexity adds latency and resource usage,
- scheduling must prioritize users with highest business impact.

This is directly relevant to practical receiver pipeline management.
