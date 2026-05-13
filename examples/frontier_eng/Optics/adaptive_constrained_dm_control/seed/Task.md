# Adaptive A1 Specification: Constrained DM Control

## Background for CS Readers

You can view this task as a constrained vector optimization problem in a noisy control loop.

- The hidden system state is optical wavefront distortion.
- The observation is a WFS slope vector `s`.
- The output is a DM command vector `u`.
- Every actuator command must stay in `[-Vmax, Vmax]`.

A pure linear map `u = R @ s` followed by clipping is valid, but usually not optimal under hard bounds.

## What You Need to Do

Edit exactly one function:

- Editable file: `baseline/init.py`
- Target function:

```python
def compute_dm_commands(slopes, reconstructor, control_model, prev_commands=None, max_voltage=0.15):
    ...
```

Goal:

- Improve `score_0_to_1_higher_is_better`.
- Keep outputs always valid (shape, finite values, bound constraints).



### Inputs

- `slopes: np.ndarray`, shape `(2 * n_subap,)`
  - current WFS slope measurement
- `reconstructor: np.ndarray`, shape `(n_act, 2 * n_subap)`
  - baseline linear map from slopes to commands
- `control_model: dict`
  - precomputed matrices/constants from `verification/evaluate.py`
  - common keys:
    - `normal_matrix`: `H^T H + lambda I`
    - `h_t`: `H^T`
    - `h_matrix`: `H`
    - `pgd_step`, `pgd_iters`
    - `ridge_design_matrix`: `[H; sqrt(beta) I]`
    - `ridge_rhs_zeros`
    - `lag_comp_gain`
- `prev_commands: np.ndarray | None`, shape `(n_act,)`
  - previous applied command
- `max_voltage: float`
  - per-actuator bound

### Output

- `dm_commands: np.ndarray`, shape `(n_act,)`
  - must satisfy:
    - correct shape
    - no NaN/Inf
    - all entries in `[-max_voltage, max_voltage]`

## Verification Scenario

`verification/evaluate.py` uses a dynamic benchmark with practical disturbances:

1. time-correlated low-order turbulence-like modes
2. additional small high-order perturbations
3. delayed/noisy slope measurements
4. actuator lag (`ACTUATOR_LAG`)
5. model mismatch between nominal and true DM gain

So this is constrained dynamic control, not just static matrix fitting.

## Metrics and Score (0 to 1, Higher is Better)

Main leaderboard field:

- `score_0_to_1_higher_is_better` in `[0, 1]`
- `score_percent = 100 * score_0_to_1_higher_is_better`

Raw metrics in `metrics.json`:

- `mean_rms` (lower better)
- `worst_rms` (lower better)
- `mean_strehl` (higher better)
- `mean_saturation_ratio` (lower better)

Weighted utility aggregation:

- `0.20 * U(mean_rms)`
- `0.10 * U(worst_rms)`
- `0.15 * U(mean_strehl)`
- `0.55 * U(mean_saturation_ratio)`

Anchors in evaluator:

- lower-better:
  - `mean_rms`: good `1.35`, bad `2.10`
  - `worst_rms`: good `2.10`, bad `3.10`
  - `mean_saturation_ratio`: good `0.02`, bad `0.35`
- higher-better:
  - `mean_strehl`: good `0.24`, bad `0.08`

`raw_cost_lower_is_better` is diagnostic only.

## Baseline Implementation

`baseline/init.py` currently does:

1. `u = reconstructor @ slopes`
2. hard clipping on `u`

## Reference Implementation

`verification/reference_controller.py` uses SciPy:

- `scipy.optimize.lsq_linear`
- bounded ridge least squares:
  - minimize `||H u - s||^2 + beta ||u||^2`
  - subject to `u_i in [-Vmax, Vmax]`
- includes delay compensation with `prev_commands` and `h_matrix`

## Output Files

Run:

```bash
python verification/evaluate.py
```

Generated in `verification/outputs/`:

- `metrics.json`
- `metrics_comparison.png`
- `example_visualization.png`

## Dependency and Constraints

- `verification/reference_controller.py` is allowed to use third-party SciPy as a reference upper bound.
- Agent edits in `baseline/init.py` should not directly call heavy external solvers to bypass the benchmark intent.
