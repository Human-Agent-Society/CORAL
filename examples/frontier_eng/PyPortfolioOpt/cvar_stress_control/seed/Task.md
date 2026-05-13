# Task 02 Specification: CVaR Stress-Controlled Allocation

## Background

You are allocating a long-only portfolio using scenario returns.
The PM requires a minimum expected return, while risk wants tail-loss control.
You therefore minimize CVaR subject to return and operational constraints.

## Input

`instance` dict fields:
- `scenario_returns`: `np.ndarray`, shape `(T, N)`
- `mu`: `np.ndarray`, shape `(N,)`, expected returns estimate
- `w_prev`: `np.ndarray`, shape `(N,)`
- `lower`: `np.ndarray`, shape `(N,)`
- `upper`: `np.ndarray`, shape `(N,)`
- `sector_ids`: `np.ndarray`, shape `(N,)`
- `sector_lower`: `dict[int, float]`
- `sector_upper`: `dict[int, float]`
- `beta`: `float` in `(0,1)` for CVaR confidence
- `target_return`: `float`
- `turnover_limit`: `float` (`||w - w_prev||_1` cap)

## Output

Return:
- `weights`: `np.ndarray` shape `(N,)`

## Objective and Constraints

Minimize CVaR of scenario loss:
- loss in scenario `t`: `L_t = -R_t^T w`
- `CVaR_beta = alpha + 1/((1-beta)T) * sum_t u_t`
- with `u_t >= L_t - alpha`, `u_t >= 0`

Subject to:
- `sum(w) == 1`
- `lower_i <= w_i <= upper_i`
- `mu^T w >= target_return`
- sector lower/upper constraints
- turnover cap via L1 distance to `w_prev`

## Expected Result

Good solutions should keep tail loss close to optimal while satisfying all constraints.

## Scoring

Per instance:
1. Compute optimal CVaR from reference: `c_ref`.
2. Compute candidate CVaR: `c_cand`.
3. Let anchor be CVaR of uniform portfolio: `c_anchor`.
4. Normalize improvement:
   - `norm = (c_anchor - c_cand) / (c_anchor - c_ref + 1e-12)`
5. Compute feasibility penalty from violated constraints.
6. Score:
   - `100 * clip(norm, 0, 1) * (1 - penalty)`

Average over instances is final score.

## Theoretical Upper Bound

This is a convex LP/SOCP-equivalent formulation. The reference CVXPY optimum is the
practical theoretical upper bound under this benchmark (score 100).

## Implementation Notes

A non-library baseline can be built as:
- estimate each asset tail risk from worst scenarios,
- create risk-adjusted scores (`mu / tail_risk`),
- convert to initial weights,
- enforce turnover and exposures,
- greedily tilt to meet return target.

This gives a feasible heuristic even without a generic solver.
