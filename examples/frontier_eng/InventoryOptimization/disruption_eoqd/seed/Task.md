# Task 05 - EOQ Optimization Under Supply Disruptions (EOQD)

## Background
This is a single-variable optimization problem with disruption risk.

- Decision variable: order quantity `Q`
- Objective: minimize disruption-aware expected cost
- Tradeoff: larger `Q` reduces order frequency risk but increases holding cost

## Engineering Scenario
A buyer sources one critical item from a disruption-prone supplier.

- Supply availability follows stochastic disruption/recovery transitions
- Demand is high and continuous
- You need `Q` that performs well in model cost and simulation service/risk indicators

## Inputs
Inputs are defined in `verification/evaluate.py` and passed to both methods.

- Cost and disruption parameters: [`verification/evaluate.py`](verification/evaluate.py)
- Baseline generator: [`baseline/init.py`](baseline/init.py)
- Stockpyl reference generator: [`verification/reference.py`](verification/reference.py)

## Outputs
Running evaluation writes:

- [`output/baseline_result.json`](output/baseline_result.json)
- [`output/reference_result.json`](output/reference_result.json)
- [`output/comparison.json`](output/comparison.json)

## Scoring (0 to 1)
`clip(x) = min(1, max(0, x))`

- `CostScore` (0.35): model-cost reduction vs baseline `Q` (`EOQD cost`)
- `ServiceScore` (0.35): simulated fill-rate target (`0.25 -> 0.60`)
- `RiskScore` (0.25): simulated stockout-event-rate reduction
- `CapitalScore` (0.05): lower average on-hand inventory is better

Final score:

`FinalScore = 0.35*CostScore + 0.35*ServiceScore + 0.25*RiskScore + 0.05*CapitalScore`

## Algorithm Mapping
Baseline (`baseline/init.py`, no stockpyl optimizer):

- Implementation style: hand-crafted heuristic/rule-based logic without invoking stockpyl optimizers.
- Input/Output contract: `solve(...)` returns task-specific policy parameters (CST/base-stock/(s,S)/Q), consumed by `verification/evaluate.py`.

- Compute classic EOQ: `sqrt(2KD/h)`
- Apply manual disruption multiplier: `Q_manual = Q_classic * (1 + 0.5*lambda/mu)`

Reference (`verification/reference.py`, stockpyl-based):

- Implementation style: calls stockpyl model-specific optimizer/DP/enumeration/heuristic APIs.
- Input/Output contract: exposes the same `solve(...)`-style policy output shape as baseline for fair evaluation.

- `stockpyl.supply_uncertainty.eoq_with_disruptions`
- EOQD optimization considering disruption and recovery rates

Evaluator (`verification/evaluate.py`):

- Calls baseline and reference directly
- Uses `eoq_with_disruptions_cost` for model-cost scoring
- Uses custom stochastic simulation for fill rate, stockout-event rate, and average inventory

## Run
```bash
cd tasks/disruption_eoqd
python verification/evaluate.py
```

## Note
Use `verification/evaluate.py` as the only required entrypoint for this task.
