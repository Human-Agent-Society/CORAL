# Task 03 Specification: Discrete Rebalance MIP

## Background

You have target portfolio weights from a model, but execution must use integer lots.
You also need to control transaction fees and turnover notional.

This is a mixed-integer linear optimization problem.

## Input

`instance` dict fields:
- `prices`: `np.ndarray`, shape `(N,)`
- `lot_sizes`: `np.ndarray`, shape `(N,)`, positive integers
- `current_lots`: `np.ndarray`, shape `(N,)`, current integer lots
- `target_weights`: `np.ndarray`, shape `(N,)`, sum close to 1
- `portfolio_value`: `float`, total budget for final holdings + fees
- `fee_rate`: `float`, proportional fee on traded notional
- `turnover_limit_value`: `float`, max traded notional
- `max_lots`: `np.ndarray`, shape `(N,)`, upper bound for each lot variable

Define unit notional per lot: `unit_i = prices_i * lot_sizes_i`.

## Output

Return:
- `lots`: `np.ndarray`, shape `(N,)`, integer final lots

Optional fields are ignored.

## Objective and Constraints

Minimize:

`sum_i |unit_i * lots_i - target_weights_i * portfolio_value| + fee_rate * traded_notional`

where:

`traded_notional = sum_i unit_i * |lots_i - current_lots_i|`

Subject to:
- `0 <= lots_i <= max_lots_i`, integer
- `traded_notional <= turnover_limit_value`
- `sum_i unit_i * lots_i + fee_rate * traded_notional <= portfolio_value`

## Expected Result

A strong solution has low target-tracking error with feasible execution constraints.

## Scoring

Per instance:
1. Compute objective of reference integer optimum: `obj_ref`.
2. Compute objective of candidate: `obj_cand`.
3. Anchor with objective of no-trade (`current_lots`): `obj_anchor`.
4. Normalize:
   - `norm = (obj_anchor - obj_cand) / (obj_anchor - obj_ref + 1e-12)`
5. Apply feasibility/integer penalty.
6. Score:
   - `100 * clip(norm, 0, 1) * (1 - penalty)`

Average score over instances is final score.

## Theoretical Bound

- Practical benchmark upper bound: reference integer optimum (`100` score).
- Additional theoretical comparator: LP relaxation lower bound (continuous lots),
  reported by evaluator for integrality-gap analysis.

## Implementation Notes

Without calling external optimizers, a solid baseline can use:
- rounded initialization from target notional,
- feasibility repair loops for budget/turnover,
- local search over +/- 1 lot moves,
- greedy fill of underweight assets when constraints allow.

This is typical for production heuristics when exact MIP is too slow.
