# Task 03 - Joint Replenishment Under Shared Ordering Cost

## Background
This is a combinational optimization problem with shared setup cost.

- Decision variables: base cycle time `T` and per-item order multiple `m_i`
- Constraint: item `i` can only be ordered every `m_i * T`
- Objective: minimize long-run total ordering + holding cost

## Engineering Scenario
A warehouse replenishes 8 SKUs jointly.

- There is one shared order setup cost for each replenishment cycle
- Each SKU has individual setup and holding cost
- You need coordinated cycles that reduce total cost while keeping slow SKUs responsive enough

## Inputs
Defined in task code and consumed by `verification/evaluate.py`.

- Shared setup, item setup, holding cost, demand rates: [`verification/evaluate.py`](verification/evaluate.py)
- Baseline policy generator: [`baseline/init.py`](baseline/init.py)
- Stockpyl reference generator: [`verification/reference.py`](verification/reference.py)

## Outputs
Running evaluation writes:

- [`output/baseline_result.json`](output/baseline_result.json)
- [`output/reference_result.json`](output/reference_result.json)
- [`output/comparison.json`](output/comparison.json)

## Scoring (0 to 1)
`clip(x) = min(1, max(0, x))`

- `CostScore` (0.55): cost reduction vs independent EOQ baseline
- `ResponsivenessScore` (0.30): max cycle-time control (`target <= 1.8`, cap at `2.6`)
- `CoordinationScore` (0.15): fewer unique multiples means better coordination

Final score:

`FinalScore = 0.55*CostScore + 0.30*ResponsivenessScore + 0.15*CoordinationScore`

## Algorithm Mapping
Baseline (`baseline/init.py`, no stockpyl optimizer):

- Implementation style: hand-crafted heuristic/rule-based logic without invoking stockpyl optimizers.
- Input/Output contract: `solve(...)` returns task-specific policy parameters (CST/base-stock/(s,S)/Q), consumed by `verification/evaluate.py`.

- Fixed-cycle + demand-bucket multiples rule
- Assign `m_i` by demand bins, then compute `Q_i = d_i * m_i * T`

Reference (`verification/reference.py`, stockpyl-based):

- Implementation style: calls stockpyl model-specific optimizer/DP/enumeration/heuristic APIs.
- Input/Output contract: exposes the same `solve(...)`-style policy output shape as baseline for fair evaluation.

- `stockpyl.eoq.joint_replenishment_problem_silver_heuristic`
- Silver heuristic for joint replenishment optimization

Evaluator (`verification/evaluate.py`):

- Calls baseline and reference directly
- Computes a common analytical cost function for both policies
- Outputs detailed metrics and final comparison

## Run
```bash
cd tasks/joint_replenishment
python verification/evaluate.py
```

## Note
Use `verification/evaluate.py` as the only required entrypoint for this task.
