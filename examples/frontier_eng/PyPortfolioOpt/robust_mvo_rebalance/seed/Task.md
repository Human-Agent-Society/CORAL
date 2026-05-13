# Task 01 Specification: Robust MVO Rebalancing

## Background

You are implementing a portfolio rebalancer for an equity strategy.
The strategy outputs expected returns `mu` and covariance `Sigma`, but risk and operations
require additional controls:
- per-asset bounds,
- sector lower/upper bounds,
- style/factor exposure bounds,
- turnover limit from current holdings,
- L1 transaction penalty.

This is a constrained convex optimization problem.

## Input

The solver receives a Python `dict` named `instance`:

- `mu`: `np.ndarray`, shape `(N,)` expected returns.
- `cov`: `np.ndarray`, shape `(N, N)` PSD covariance matrix.
- `w_prev`: `np.ndarray`, shape `(N,)`, current portfolio weights.
- `lower`: `np.ndarray`, shape `(N,)`, lower bounds.
- `upper`: `np.ndarray`, shape `(N,)`, upper bounds.
- `sector_ids`: `np.ndarray`, shape `(N,)`, integer sector id per asset.
- `sector_lower`: `dict[int, float]` lower exposure by sector.
- `sector_upper`: `dict[int, float]` upper exposure by sector.
- `factor_loadings`: `np.ndarray`, shape `(N, K)`, asset exposures to K risk factors.
- `factor_lower`: `np.ndarray`, shape `(K,)`, lower bound for portfolio factor exposure.
- `factor_upper`: `np.ndarray`, shape `(K,)`, upper bound for portfolio factor exposure.
- `risk_aversion`: `float`.
- `transaction_penalty`: `float`.
- `turnover_limit`: `float`, L1 turnover cap.

## Output

Return a `dict` with:
- `weights`: `np.ndarray` shape `(N,)`.

Optional fields are ignored by evaluator.

## Objective and Constraints

Maximize:

`mu^T w - risk_aversion * w^T cov w - transaction_penalty * ||w - w_prev||_1`

Subject to:
- `sum(w) == 1`
- `lower_i <= w_i <= upper_i`
- sector constraints:
  - `sector_lower[s] <= sum_{i in sector s} w_i <= sector_upper[s]`
- factor exposure constraints:
  - `factor_lower[k] <= sum_i factor_loadings[i, k] * w_i <= factor_upper[k]`
- turnover:
  - `||w - w_prev||_1 <= turnover_limit`

## Expected Result

A high-quality solution should:
- be feasible up to numerical tolerance,
- achieve objective value close to the convex optimum.

## Scoring

For each test instance:
1. Compute reference optimal objective `f_ref`.
2. Compute candidate objective `f_cand`.
3. Build a normalized score against a naive anchor:
   - `f_anchor = min(f_uniform, f_prev_holdings)`
   - `norm = (f_cand - f_anchor) / (f_ref - f_anchor + 1e-12)`
4. Apply feasibility penalty:
   - each violated constraint contributes penalty; total penalty clipped to `[0, 1]`.
5. Instance score:
   - `100 * clip(norm, 0, 1) * (1 - penalty)`

Final score is the average over all instances.

## Theoretical Upper Bound

Because this is a convex problem, the reference solution (CVXPY global optimum)
is the practical theoretical upper bound under this formulation.
Its score is `100`.

## Implementation Notes

A practical non-library baseline can use:
- projected gradient ascent on a smoothed objective,
- iterative repair/projection for constraints:
  - clip to bounds,
  - enforce turnover by shrinking delta from `w_prev`,
  - enforce sector bounds by proportional redistribution,
  - renormalize to `sum(w)=1`.

This baseline is not globally optimal but should produce feasible solutions.

## Baseline Implementation (this repo)

- File: `baseline/init.py`
- Method class: projected first-order heuristic (no external optimizer)
- Core idea:
  - smooth the L1 term and take gradient steps on the objective,
  - repeatedly repair weights to satisfy bounds, sector limits, turnover, and budget sum.
- Characteristic:
  - fast and dependency-light,
  - does not explicitly project onto factor-exposure constraints,
  - does not guarantee global optimality.

## Reference Implementation (this repo)

- File: `verification/reference.py`
- Method class: exact convex optimization with CVXPY
- Core idea:
  - solve the full objective and all constraints in one optimization program,
  - includes asset/sector/factor/turnover constraints explicitly.
- Characteristic:
  - returns the practical optimum (or near-optimum if solver reports `optimal_inaccurate`),
  - used as scoring upper bound in this benchmark.
