# Torsion Profile Fitting

## One-Line Summary

Tune a few continuous parameters so that the predicted energy curve matches a target curve as closely as possible.

## Background

When a molecule rotates around a bond, different dihedral angles usually have different energies.
Plotting angle against relative energy gives a torsion profile.

If the force-field parameters are not suitable, the predicted curve will not match the target curve.

So the task is:

- tune a few scale parameters
- make the predicted curve match the target curve

## What `baseline/init.py` Receives

`prepare` emits a pure algorithm JSON:

```json
{
  "task_name": "torsion_profile_fitting_demo",
  "angles_degrees": [60, 120, 180, 240, 300],
  "tunable_terms": ["k1", "k2", "k3"],
  "term_scale_bounds": {
    "k1": [0.6, 1.8],
    "k2": [0.6, 1.8],
    "k3": [0.6, 1.8]
  },
  "score_penalty_per_rmse": 250.0,
  "target_relative_energies_kcal_per_mol": [4.6, 6.2, 0.0, 6.5, 8.6],
  "candidate_profiles": [
    {
      "candidate_id": "sample_0000",
      "term_scales": {"k1": 0.8, "k2": 1.2, "k3": 1.0},
      "relative_energies_kcal_per_mol": [4.1, 5.8, 0.0, 6.1, 8.1]
    }
  ]
}
```

The key point is:

- `candidate_profiles`
  - are public samples
- they do not define the full search space

## Output Format

```json
{
  "term_scales": {
    "k1": 1.2,
    "k2": 1.6,
    "k3": 1.0
  }
}
```

Rules:

- every parameter must be provided
- every value must lie within `term_scale_bounds`

## Scoring

First compute the RMSE between the predicted and target curves:

`rmse = sqrt(mean((predicted_i - target_i)^2))`

Then convert it into a score:

`score = max(0, 100 - score_penalty_per_rmse * rmse)`

So:

- lower RMSE is better
- higher score is better

## How the Reference Values Are Obtained

This task reports two useful reference values:

- `public_sample_best_score`
- `known_optimal_score`

They come from different places:

- `public_sample_best_score`
  - evaluation checks every profile in `candidate_profiles`
  - computes its RMSE against the target
  - converts that RMSE into a score
  - keeps the best one
- `known_optimal_score`
  - is not rediscovered online during evaluation
  - it is written into `data/raw_task.json` when the benchmark is defined

In the current benchmark:

- `known_optimal_score = 100.0`

This is the theoretical top score allowed by the scoring formula.

## Current Starter Level

With the current configuration measured on `2026-03-16`:

- starter score
  - `34.744169`
- known optimum
  - `100.0`
- relative gap
  - `65.256%`
- best public-sample score
  - `81.876024`

## Why the Starter Is Weak

The current `baseline/init.py` is intentionally weak:

- it fixes all scales at `1.0`
- it completely ignores `candidate_profiles`

So it does not even perform the simplest upgrade of picking the best public sample.

## Where to Improve First

A strong first path is:

1. pick the best public sample
2. fit a surrogate model on public samples
3. optimize continuously on that surrogate

## What the Chemistry Stack Does

[verification/evaluate.py](verification/evaluate.py)

- `prepare`
  - generates public parameter samples
  - computes a full energy profile for each sample
- `evaluate`
  - writes your submitted scales back into the force field
  - recomputes the profile and the final score

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
