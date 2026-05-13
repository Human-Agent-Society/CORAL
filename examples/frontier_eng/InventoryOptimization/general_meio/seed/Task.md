# Task 02 - General Multi-Echelon Inventory Optimization (MEIO)

## Background
This is a network optimization problem with stochastic demand.

- Graph: 5-node DAG (`10 -> {20,30} -> {40,50}`)
- Decision variable: base-stock level at each node
- Objective: balance cost and service under random demand
- Constraint: avoid unfair service allocation across sinks

## Engineering Scenario
A two-layer distribution network serves two customer-facing markets.

- Nodes 40 and 50 face external demand
- Demand is Poisson and increases in stress scenario (`x1.2`)
- You need one base-stock policy that performs well on cost, service, robustness, and sink balance

## Inputs
All inputs are encoded in task code and executed by `verification/evaluate.py`.

- Network topology, lead times, cost parameters: [`verification/evaluate.py`](verification/evaluate.py)
- Baseline/reference policy generation:
  - baseline: [`baseline/init.py`](baseline/init.py)
  - stockpyl reference: [`verification/reference.py`](verification/reference.py)
- Simulation settings:
  - nominal: `demand_scale=1.0`, `periods=160`, `seed=11`
  - stress: `demand_scale=1.2`, `periods=160`, `seed=17`

## Outputs
Running evaluation writes:

- [`output/baseline_result.json`](output/baseline_result.json)
- [`output/reference_result.json`](output/reference_result.json)
- [`output/comparison.json`](output/comparison.json)

## Scoring (0 to 1)
`clip(x) = min(1, max(0, x))`

- `CostScore` (0.30): nominal cost-per-period reduction
- `ServiceScore` (0.35): nominal weighted fill-rate target (`0.98 -> 0.995`)
- `RobustnessScore` (0.25): stress cost-per-period reduction
- `BalanceScore` (0.10): sink fill-rate fairness (`|fill40-fill50|`)

Final score:

`FinalScore = 0.30*CostScore + 0.35*ServiceScore + 0.25*RobustnessScore + 0.10*BalanceScore`

## Algorithm Mapping
Baseline (`baseline/init.py`, no stockpyl optimizer):

- Implementation style: hand-crafted heuristic/rule-based logic without invoking stockpyl optimizers.
- Input/Output contract: `solve(...)` returns task-specific policy parameters (CST/base-stock/(s,S)/Q), consumed by `verification/evaluate.py`.

- Manual demand-coverage heuristic
- Base stock computed by fixed multipliers on sink means and upstream aggregation

Reference (`verification/reference.py`, stockpyl-based):

- Implementation style: calls stockpyl model-specific optimizer/DP/enumeration/heuristic APIs.
- Input/Output contract: exposes the same `solve(...)`-style policy output shape as baseline for fair evaluation.

- `stockpyl.meio_general.meio_by_enumeration`
- Enumerative MEIO search with grouped decision variables

Evaluator (`verification/evaluate.py`):

- Calls baseline and reference directly
- Simulates both with the same seeds and periods (`stockpyl.sim.simulation`)
- Computes weighted fill-rate, cost metrics, final score, and comparison

## Run
```bash
cd tasks/general_meio
python verification/evaluate.py
```

## Note
Use `verification/evaluate.py` as the only required entrypoint for this task.
