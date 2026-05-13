# Adaptive A3 Specification: Energy-Aware Control

## Background

This task is a **multi-objective optimization** problem.

In AO control, minimizing residual error alone often produces large and dense command vectors. In real systems, command magnitude maps to practical costs:

- actuator power and thermal load,
- long-term reliability,
- electronics margin.

So we optimize correction quality and command energy together.

## What You Need to Do

Edit a single function:

- File: `baseline/init.py`
- Function:

```python
def compute_dm_commands(slopes, reconstructor, control_model, prev_commands=None, max_voltage=0.35):
    ...
```

Goal:
- Maximize `score_0_to_1_higher_is_better`.
- Respect validity constraints at every call.



### Inputs

- `slopes: np.ndarray`, shape `(2 * n_subap,)`
  - Current delayed/noisy slope vector.
- `reconstructor: np.ndarray`, shape `(n_act, 2 * n_subap)`
  - Baseline linear map.
- `control_model: dict`
  - Includes sparse-control parameters and dynamics hints:
    - `h_matrix`
    - `lasso_alpha`, `lasso_max_iter`, `lasso_tol`
    - `delay_comp_gain`
    - `temporal_blend`
- `prev_commands: np.ndarray | None`, shape `(n_act,)`
  - Previous command (optional, useful for temporal robustness).
- `max_voltage: float`
  - Hard per-channel bound.

### Output

- `dm_commands: np.ndarray`, shape `(n_act,)`
  - Must have correct shape, finite values, and satisfy bounds.

## Verification Scenario

`verification/evaluate.py` builds a dynamic benchmark with delayed sensing and mismatch:

1. Time-correlated modal phase evolution.
2. Delayed and noisy WFS slopes.
3. Actuator lag in applied commands.
4. True plant gain mismatch vs nominal model.

This setup makes pure residual minimization less competitive than energy-aware strategies.

## Metrics and Score (0 to 1, Higher is Better)

Leaderboard field:
- `score_0_to_1_higher_is_better` in `[0, 1]`
- `score_percent = 100 * score_0_to_1_higher_is_better`

Raw metrics:
- `mean_rms` (lower better)
- `mean_abs_command` (lower better)
- `mean_sparsity` (higher better, fraction near zero)
- `mean_strehl` (higher better)

Weighted utility score:
- `0.15 * U(mean_rms)`
- `0.60 * U(mean_abs_command)`
- `0.15 * U(mean_sparsity)`
- `0.10 * U(mean_strehl)`

Anchors:
- lower-better:
  - `mean_rms`: good `1.55`, bad `2.25`
  - `mean_abs_command`: good `0.08`, bad `0.36`
- higher-better:
  - `mean_sparsity`: good `0.40`, bad `0.00`
  - `mean_strehl`: good `0.22`, bad `0.08`

`raw_cost_lower_is_better` remains diagnostic only.

## Baseline Implementation

Current baseline (`baseline/init.py`):
1. `u = reconstructor @ slopes`
2. `clip` to bounds

Weakness:
- no explicit energy regularization
- tends to produce high-amplitude dense commands

## Oracle / Reference Implementation

Reference (`verification/reference_controller.py`) uses third-party `scikit-learn` Lasso:

- solver: `sklearn.linear_model.Lasso`
- objective in implementation form:
  - `(1/(2m)) * ||H u - s||^2 + alpha * ||u||_1`
- optional delay compensation via `prev_commands`
- temporal blending for stability
- final clipping for box constraints

Why this is a strong comparator:
- standardized sparse optimization backend
- naturally promotes lower energy and higher sparsity

## Verification Outputs: What They Mean

Run:

```bash
python verification/evaluate.py
```

Outputs in `verification/outputs/`:

- `metrics.json`
  - Structured report with baseline/reference metrics and score metadata.
  - Primary artifact for automated evaluation.
- `metrics_comparison.png`
  - Visual bar-chart comparison of key metrics and score.
- `example_visualization.png`
  - Representative phase/residual/PSF pair for baseline and reference.
  - Useful to visually confirm quality-energy tradeoff behavior.

## Dependency and Policy

- Baseline is expected to stay lightweight (`numpy` + provided matrices).
- Reference is allowed to use third-party `scikit-learn`.
- Thread-count tuning is not considered a valid optimization approach.
