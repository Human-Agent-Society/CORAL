# Weighted Parameter Coverage

## One-Line Summary

Select a small subset of candidates under a budget so that the covered high-value features are as large as possible.

## Background

In real OpenFF workflows, each molecule activates a set of force-field parameters.

A good test set is not just “many molecules”. It should:

- use as few molecules as possible
- cover as many parameters as possible
- especially cover rare parameters

This benchmark already converts the chemistry side into a pure combinatorial optimization problem.

## What `baseline/init.py` Receives

`prepare` produces a pure algorithm JSON:

```json
{
  "task_name": "rare_parameter_coverage_demo",
  "budget": 4,
  "feature_weights": {
    "feat_1": 1.0,
    "feat_2": 0.5
  },
  "candidates": [
    {
      "candidate_id": "mol_000",
      "name": "aspirin",
      "covered_features": ["feat_1", "feat_2"]
    }
  ]
}
```

Interpretation:

- `budget`
  - maximum number of candidates you may select
- `feature_weights`
  - value of each feature
- `covered_features`
  - which features each candidate covers

## Output Format

`baseline/init.py` must write:

```json
{
  "selected_candidate_ids": ["mol_001", "mol_007"]
}
```

Rules:

- you may not exceed `budget`
- you may not repeat a candidate

## Scoring

Let `U` be the union of all covered features from the selected candidates.

The score is:

`score = sum(feature_weights[f] for f in U)`

Higher is better.

## How the Reference Values Are Obtained

This task reports:

- `exact_optimal_score`
- `certified_upper_bound`

They are identical here because evaluation solves the prepared instance exactly as a MILP:

- `x_i`
  - whether candidate `i` is selected
- `y_f`
  - whether feature `f` is covered

Objective:

- maximize `sum(feature_weights[f] * y_f)`

Constraints:

- `sum(x_i) <= budget`
- `y_f` can only be `1` if at least one selected candidate covers feature `f`

Therefore:

- `exact_optimal_score`
  - is the true optimum for the current instance
- `certified_upper_bound`
  - is equal to that same exact optimum

## Current Starter Level

With the current configuration measured on `2026-03-16`:

- starter score
  - `9.077764`
- exact optimum
  - `24.579023`
- relative gap
  - `63.067%`

## Why the Starter Is Weak

The current `baseline/init.py` is intentionally simple:

- it ranks candidates only by standalone coverage count
- it ignores overlap between candidates
- it does not directly target rarer, higher-value features

So it tends to pick candidates that look large individually but combine poorly.

## Where to Improve First

The most useful first upgrades are:

1. replace static ranking with marginal-gain greedy selection
2. add `1-swap` or `2-swap` local search
3. run multiple random restarts

## What the Chemistry Stack Does

[verification/evaluate.py](verification/evaluate.py)

- `prepare`
  - uses OpenFF Toolkit to convert molecules into feature sets
- `evaluate`
  - scores the selected subset
  - solves the exact optimum with MILP

## Raw Input

[data/raw_task.json](data/raw_task.json)

## How to Run

Run from this task directory:

```bash
mkdir -p outputs

python verification/evaluate.py prepare \
  --raw-task data/raw_task.json \
  --prepared-output outputs/prepared.json

python baseline/init.py \
  --prepared-input outputs/prepared.json \
  --solution-output outputs/solution.json

python verification/evaluate.py evaluate \
  --prepared-input outputs/prepared.json \
  --solution outputs/solution.json \
  --result-output outputs/result.json
```
