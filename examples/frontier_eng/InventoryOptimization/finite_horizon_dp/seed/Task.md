# Task 04 - Finite-Horizon Stochastic Inventory Control (DP)

## Background
This is a finite-horizon stochastic control problem.

- Horizon: 8 periods
- State: current inventory level
- Action: order quantity (equivalently `(s_t, S_t)` policy)
- Objective: minimize expected total cost with random demand and terminal penalty

## Engineering Scenario
A plant manages one SKU across a short planning horizon with demand spikes.

- Demand mean and variance are time-varying
- Fixed order setup cost discourages frequent small orders
- Stockout penalty is high, but excessive stock also costs holding/capital

You need a period-dependent policy that balances these tradeoffs.

## Inputs
Inputs are defined in `verification/evaluate.py` and passed into both methods.

- Full cost configuration and demand profile: [`verification/evaluate.py`](verification/evaluate.py)
- Baseline policy generator: [`baseline/init.py`](baseline/init.py)
- DP reference policy generator: [`verification/reference.py`](verification/reference.py)

## Outputs
Running evaluation writes:

- [`output/baseline_result.json`](output/baseline_result.json)
- [`output/reference_result.json`](output/reference_result.json)
- [`output/comparison.json`](output/comparison.json)

## Scoring (0 to 1)
`clip(x) = min(1, max(0, x))`

Scores are computed from Monte Carlo simulation (`1500` trials, same seed for fairness).

- `CostScore` (0.55): expected total-cost reduction vs baseline order-up-to policy
- `ServiceScore` (0.40): average fill-rate target (`0.94 -> 0.975`)
- `CadenceScore` (0.05): order-count reduction vs baseline

Final score:

`FinalScore = 0.55*CostScore + 0.40*ServiceScore + 0.05*CadenceScore`

## Algorithm Mapping
Baseline (`baseline/init.py`, no stockpyl DP):

- Implementation style: hand-crafted heuristic/rule-based logic without invoking stockpyl optimizers.
- Input/Output contract: `solve(...)` returns task-specific policy parameters (CST/base-stock/(s,S)/Q), consumed by `verification/evaluate.py`.

- Manual moment-based time-varying rule
- `s_t = round(0.60 * mean_t)`
- `S_t = max(round(mean_t + 1.10*sd_t + 32), s_t + 6)`

Reference (`verification/reference.py`, stockpyl-based):

- Implementation style: calls stockpyl model-specific optimizer/DP/enumeration/heuristic APIs.
- Input/Output contract: exposes the same `solve(...)`-style policy output shape as baseline for fair evaluation.

- `stockpyl.finite_horizon.finite_horizon_dp`
- Dynamic programming for optimal finite-horizon `(s,S)` policy

Evaluator (`verification/evaluate.py`):

- Calls baseline and reference directly
- Simulates both policies under identical random demand generation
- Produces metric-level breakdown and final comparison

## Run
```bash
cd tasks/finite_horizon_dp
python verification/evaluate.py
```

## Note
Use `verification/evaluate.py` as the only required entrypoint for this task.
