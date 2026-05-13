# Diverse Conformer Portfolio

## One-Line Summary

For each molecule, select a fixed-size set of conformers that are both low-energy and diverse from one another.

## Background

A molecule usually has many possible 3D conformers.

If you only select the lowest-energy conformers, they are often very similar.
If you only maximize diversity, you may keep unstable conformers.

So this task balances:

- stability
- diversity

## What `baseline/init.py` Receives

`prepare` emits a pure algorithm JSON:

```json
{
  "task_name": "diverse_conformer_portfolio_demo",
  "portfolio_size": 3,
  "energy_weight": 0.5,
  "diversity_weight": 3.0,
  "energy_cap_kcal_per_mol": 4.0,
  "rmsd_cap_angstrom": 2.5,
  "diversity_reward_exponent": 2.0,
  "molecules": [
    {
      "molecule_id": "mol_000",
      "conformers": [
        {
          "conformer_id": "mol_000_conf_000",
          "relative_energy_kcal_per_mol": 0.0
        }
      ],
      "pairwise_rmsd_angstrom": [
        [0.0, 1.2],
        [1.2, 0.0]
      ]
    }
  ]
}
```

This is a fixed-size subset selection problem:

- each conformer has a node reward
- each selected pair has an extra pair reward
- you must pick exactly `portfolio_size` conformers

## Output Format

```json
{
  "selected_conformer_ids": {
    "mol_000": ["mol_000_conf_001", "mol_000_conf_004", "mol_000_conf_007"]
  }
}
```

Rules:

- every molecule must have a selection
- every molecule must select exactly `portfolio_size` conformers
- no duplicates

## Scoring

For a selected set `S`:

`score(S) = sum(node_reward(i) for i in S) + sum(pair_reward(i, j) for i < j, i,j in S)`

where:

- `node_reward(i) = energy_weight * max(0, energy_cap - relative_energy_i)`
- `pair_reward(i, j) = diversity_weight * min(rmsd_ij, rmsd_cap) ^ diversity_reward_exponent`

The total task score is the sum across molecules.

## How the Certified Upper Bound Is Obtained

This task does not solve the true optimum online. Instead it builds a valid upper bound.

For one molecule, evaluation:

1. computes all node rewards
   - keeps the top `portfolio_size`
2. computes all pair rewards
   - keeps the top `C(portfolio_size, 2)`
3. adds both sums together

That value must be at least as large as any valid subset score, so it is a certified upper bound.

But it is not an exact optimum, because:

- the best nodes
- and the best edges

may not come from the same feasible subset.

## Current Starter Level

With the current configuration measured on `2026-03-16`:

- starter score
  - `278.215531`
- certified upper bound
  - `674.897119`
- relative gap
  - `58.777%`

## Why the Starter Is Weak

The current `baseline/init.py`:

- finds the lowest-energy conformer
- then keeps conformers closest to that one

This traps the solution in a small local neighborhood.

However, the benchmark strongly rewards diversity, so a tightly clustered selection tends to waste budget.

## Where to Improve First

A practical upgrade path is:

1. replace the current heuristic with marginal-gain greedy selection
2. add `1-swap` local search
3. use multiple restarts

Further options:

- beam search
- tabu search
- quadratic integer programming

## What the Chemistry Stack Does

[verification/evaluate.py](verification/evaluate.py)

- `prepare`
  - generates conformers
  - computes energies
  - computes pairwise RMSD
- `evaluate`
  - scores submitted subsets
  - computes the certified upper bound

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
