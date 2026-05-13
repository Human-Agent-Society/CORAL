# Adaptive A4 Specification: Fault-Tolerant Sensor Fusion

## Background for CS Readers

This task is a **robust estimation + control** problem.

You receive measurements from multiple sensors (`n_wfs` channels). Some channels are corrupted by severe faults. If you simply average all channels, outliers dominate the fused signal and degrade control.

So the key challenge is: **robustly fuse multi-sensor slopes before DM control**.

## What You Need to Do

Edit one function:

- File: `baseline/init.py`
- Function:

```python
def fuse_and_compute_dm_commands(slopes_multi, reconstructor, control_model, prev_commands=None, max_voltage=0.50):
    ...
```

Goal:
- Maximize `score_0_to_1_higher_is_better` under severe sensor faults.
- Keep output always valid.



### Inputs

- `slopes_multi: np.ndarray`, shape `(n_wfs, 2 * n_subap)`
  - One slope vector per WFS channel.
- `reconstructor: np.ndarray`, shape `(n_act, 2 * n_subap)`
  - Linear map from fused slopes to DM commands.
- `control_model: dict`
  - Optional robust-fusion settings and helper objects.
  - In reference path it includes an anomaly model and fusion hyperparameters.
- `prev_commands: np.ndarray | None`, shape `(n_act,)`
  - Optional previous command.
- `max_voltage: float`
  - Command bound.

### Output

- `dm_commands: np.ndarray`, shape `(n_act,)`
  - Must be finite and bounded in `[-max_voltage, max_voltage]`.

## Verification Scenario (v3_fault_stress)

`verification/evaluate.py` uses a fault-dominant benchmark:

1. Generate true phase and clean slopes.
2. Simulate 5 WFS channels.
3. Randomly corrupt 3 channels per case with combinations of:
   - gain error,
   - additive bias/noise,
   - sparse spikes,
   - partial dropout.
4. Controller receives only corrupted multi-sensor slopes.

This is intentionally difficult and designed to expose non-robust fusion strategies.

## Metrics and Score (0 to 1, Higher is Better)

Leaderboard field:
- `score_0_to_1_higher_is_better` in `[0, 1]`
- `score_percent = 100 * score_0_to_1_higher_is_better`

Raw metrics:
- `mean_rms` (lower better)
- `p95_rms` (lower better)
- `worst_rms` (lower better, diagnostic)
- `mean_strehl` (higher better)

Weighted utility score:
- `0.45 * U(mean_rms)`
- `0.35 * U(p95_rms)`
- `0.20 * U(mean_strehl)`

Anchors:
- lower-better:
  - `mean_rms`: good `0.95`, bad `1.75`
  - `p95_rms`: good `1.20`, bad `2.05`
- higher-better:
  - `mean_strehl`: good `0.35`, bad `0.18`

`raw_cost_lower_is_better` is for diagnostics only.

## Baseline Implementation

Current baseline (`baseline/init.py`):
1. `fused = mean(slopes_multi, axis=0)`
2. `u = reconstructor @ fused`
3. clip to bounds

Weakness:
- plain mean is highly sensitive to outliers and corrupted channels

## Oracle / Reference Implementation

Reference (`verification/reference_controller.py`) uses anomaly-aware fusion:

- third-party model: `sklearn.ensemble.IsolationForest`
- trained on clean slope vectors in evaluator setup
- online steps:
  - score each sensor channel by normality
  - keep top inlier channels
  - weighted fusion with softmax-like weights
  - optional delay/temporal blending hooks
  - linear control + clipping

Why this is stronger:
- explicitly models sensor abnormality instead of assuming all channels are equally reliable

## Verification Outputs: What They Mean

Run:

```bash
python verification/evaluate.py
```

Output files in `verification/outputs/`:

- `metrics.json`
  - Structured baseline/reference report with score, raw metrics, and benchmark metadata.
  - Main artifact for automatic scoring and reproducibility.
- `metrics_comparison.png`
  - Bar chart for score + key metrics.
  - Quickly shows whether your fusion strategy improves robustness.
- `example_visualization.png`
  - Representative phase/residual/PSF comparison.
  - Useful for checking if metric gain corresponds to visibly better residual correction.

## Dependency and Policy

- Baseline should stay lightweight (`numpy` + provided matrices).
- Reference is allowed to use third-party `scikit-learn` (`IsolationForest`).
- Thread-based tuning is not considered valid optimization.
