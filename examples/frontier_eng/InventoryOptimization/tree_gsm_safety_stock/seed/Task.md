# Task 01 - Tree Supply Chain Strategic Safety-Stock Placement (GSM DP)

## Background
Treat this as a constrained optimization problem on a tree under demand uncertainty.

- Graph: `1 -> 3 -> {2,4}`
- Decision variable: committed service time (CST) at each node
- Objective: minimize expected inventory-related cost
- Constraint: demand-facing nodes must satisfy SLA limits

## Engineering Scenario
A factory serves two markets through one intermediate node.

- Node 2: premium market (strict SLA, `CST <= 0`)
- Node 4: standard market (`CST <= 1`)
- Stress scenario: demand volatility increases by 30%

You need a CST policy that keeps cost low in nominal demand and remains robust in stress demand.

## Inputs
Inputs are defined in the task code and consumed by `verification/evaluate.py`.

- Tree topology, costs, processing times, CST bounds (stockpyl model builder): [`verification/reference.py`](verification/reference.py)
- Stress test setting (`demand_scale=1.3`) and scoring thresholds: [`verification/evaluate.py`](verification/evaluate.py)
- Baseline comparison policy: `{1:0, 3:0, 2:0, 4:0}`

## Outputs
Running evaluation produces:

- [`output/baseline_result.json`](output/baseline_result.json)
- [`output/reference_result.json`](output/reference_result.json)
- [`output/comparison.json`](output/comparison.json)

## Scoring (0 to 1)
`clip(x) = min(1, max(0, x))`

- `CostScore` (0.35): nominal cost improvement vs baseline
- `RobustnessScore` (0.35): stress cost improvement vs baseline
- `SLACompliance` (0.10): SLA satisfaction on nodes 2 and 4
- `ComplexityScore` (0.20): full score only if changed nodes `<= 1`

Final score:

`FinalScore = 0.35*CostScore + 0.35*RobustnessScore + 0.10*SLACompliance + 0.20*ComplexityScore`

## Algorithm Mapping
Baseline (`baseline/init.py`, no stockpyl optimizer):

- Implementation style: hand-crafted heuristic/rule-based logic without invoking stockpyl optimizers.
- Input/Output contract: `solve(...)` returns task-specific policy parameters (CST/base-stock/(s,S)/Q), consumed by `verification/evaluate.py`.

- Rule-based CST assignment
- Demand-facing nodes fixed by SLA: node 2 -> 0, node 4 -> 1
- Internal nodes use processing-time threshold (`processing_time >= 2 => CST=1`, else `0`)

Reference (`verification/reference.py`, stockpyl-based):

- Implementation style: calls stockpyl model-specific optimizer/DP/enumeration/heuristic APIs.
- Input/Output contract: exposes the same `solve(...)`-style policy output shape as baseline for fair evaluation.

- `stockpyl.gsm_tree.optimize_committed_service_times`
- Dynamic programming on GSM tree to optimize CST

Evaluator (`verification/evaluate.py`):

- Calls baseline and reference directly
- Uses `stockpyl.gsm_helpers.solution_cost_from_cst` for consistent cost evaluation
- Writes per-method results + final comparison

## Run
```bash
cd tasks/tree_gsm_safety_stock
python verification/evaluate.py
```

## Note
Use `verification/evaluate.py` as the only required entrypoint for this task.
