# Adaptive A2 Specification: Temporal Smooth Control

## Background

This task is a **sequential decision/control** problem.

In each frame you map sensor slopes `s_t` to DM commands `u_t`. Optimizing each frame independently can reduce instantaneous error, but may create high-frequency command jitter. In real hardware this causes:

- actuator wear,
- vibration risk,
- reduced closed-loop stability margin.

So the goal is not only accuracy, but also smooth temporal behavior.

## What You Need to Do

Edit one function in one file:

- Editable file: `baseline/init.py`
- Function:

```python
def compute_dm_commands(slopes, reconstructor, control_model, prev_commands, max_voltage=0.25):
    ...
```

Goal:
- Maximize `score_0_to_1_higher_is_better`.
- Keep output always valid under the interface contract.



### Inputs

- `slopes: np.ndarray`, shape `(2 * n_subap,)`
  - Current delayed/noisy WFS slopes.
- `reconstructor: np.ndarray`, shape `(n_act, 2 * n_subap)`
  - Baseline linear mapping.
- `control_model: dict`
  - Precomputed control matrices and gains:
    - `smooth_reconstructor`
    - `prev_blend`
    - `reconstructor`
    - `delay_prediction_gain`
    - `command_lowpass`
- `prev_commands: np.ndarray`, shape `(n_act,)`
  - Previous applied command (required for temporal strategies).
- `max_voltage: float`
  - Command bound.

### Output

- `dm_commands: np.ndarray`, shape `(n_act,)`
  - Must be finite and bounded in `[-max_voltage, max_voltage]`.

## Verification Scenario

The evaluator simulates a realistic temporal AO process:

1. Modal turbulence evolves stochastically over time.
2. Sensor slopes are delayed and noisy.
3. Actuator has first-order lag.
4. Actuator rate limit is enforced (`ACTUATOR_RATE_LIMIT`).
5. True plant has gain mismatch versus nominal model.

A good controller should avoid overreacting to delayed data and should reduce command slew.

## Metrics and Score (0 to 1, Higher is Better)

Leaderboard target:
- `score_0_to_1_higher_is_better` in `[0, 1]`
- `score_percent = 100 * score_0_to_1_higher_is_better`

Raw metrics:
- `mean_rms` (lower better)
- `mean_slew = mean(|u_t - u_{t-1}|)` (lower better)
- `mean_strehl` (higher better)

Weighted utility score:
- `0.20 * U(mean_rms)`
- `0.65 * U(mean_slew)`
- `0.15 * U(mean_strehl)`

Anchors:
- lower-better:
  - `mean_rms`: good `1.45`, bad `2.10`
  - `mean_slew`: good `0.045`, bad `0.19`
- higher-better:
  - `mean_strehl`: good `0.24`, bad `0.10`

`raw_cost_lower_is_better` is diagnostic only.

## Baseline Implementation

Current baseline (`baseline/init.py`):
1. Compute `u = reconstructor @ slopes`
2. Clip to `[-Vmax, Vmax]`

Weakness:
- Ignores `prev_commands`
- Ignores smoothness objective
- Does not compensate delayed sensing

## Oracle / Reference Implementation

Reference (`verification/reference_controller.py`) uses an analytical smooth controller:

- core smooth term from precomputed matrices:
  - `u = smooth_reconstructor @ slopes + prev_blend @ prev_commands`
- delay-aware feed-forward correction:
  - uses `delay_prediction_gain`
- optional low-pass blending with previous command:
  - `command_lowpass`
- final box projection by clipping

This is still lightweight (no heavy external optimizer) but significantly stronger than frame-wise independent control.

## Verification Outputs: What They Mean

Running:

```bash
python verification/evaluate.py
```

produces in `verification/outputs/`:

- `metrics.json`
  - Full numeric report for candidate baseline and reference.
  - Includes score, raw metrics, profile constants, anchors, and weights.
- `metrics_comparison.png`
  - Side-by-side metric bars for quick comparison.
- `example_visualization.png`
  - Representative phase/residual/PSF visualization for baseline and reference.
  - Helps verify that better score corresponds to physically better correction.

## Dependency and Policy

- Baseline should remain lightweight (`numpy` + provided matrices).
- Reference is analytical and does not require third-party optimization solver.
- Thread changes are not a valid strategy for leaderboard improvement.
