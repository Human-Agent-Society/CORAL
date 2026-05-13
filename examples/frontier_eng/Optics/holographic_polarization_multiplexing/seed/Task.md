# Holographic H4 Specification: Polarization Multiplexing

## Engineering background

In polarization multiplexing, the same optical element should behave differently for different input polarization states.

In this task:

- x-polarized input should produce pattern X,
- y-polarized input should produce pattern Y,
- and cross-channel leakage should be low.

CS analogy:

- one shared model,
- two input modes,
- mode-conditioned outputs must be different and controlled.

Applications:

- polarization-division multiplexing,
- optical security,
- multifunctional diffractive/meta-optics.

Economic value:

- one element providing multiple functions lowers hardware count and integration cost.

## What you need to do

Improve baseline optimization so the design better separates polarization channels while matching per-channel target patterns and ratios.

Editable file:

- `baseline/init.py`

Read-only references:

- `verification/evaluate.py`
- `verification/reference_solver.py`

## Core file/function to modify

Primary function:

- `solve(spec, device=None, seed=0)` in `baseline/init.py`

Keep return contract compatible.

## Input contract (`spec`)

Main fields:

- optical setup:
  - `shape`, `spacing`, `wavelength`, `layer_z`, `output_z`, `waist_radius`
- channel-X target:
  - `pattern_x_centers`, `pattern_x_ratios`
- channel-Y target:
  - `pattern_y_centers`, `pattern_y_ratios`
- `roi_radius_m`

Evaluator adds:

- scoring constants (`score_eff_target`, `score_ratio_scale`),
- validity thresholds,
- better-than-baseline margins.

## Output contract (`solve`)

Required return keys:

- `output_field_x`, `output_field_y`
- `target_map_x`, `target_map_y`
- `loss_history`
- plus input/spec fields used by evaluator (`input_field_x`, `input_field_y`, `spec` recommended)

Evaluator reads these fields directly to compute channel metrics.

## Baseline implementation (current)

Current baseline is intentionally simple:

1. Build x-polarized and y-polarized Gaussian inputs.
2. Use diagonal Jones phase layers (separate phase maps for Ex/Ey channels).
3. Optimize normalized map MSE for both channels.

What it does not explicitly optimize:

- channel crosstalk,
- per-channel ratio accuracy,
- channel own-efficiency.

## Oracle implementation (current)

`verification/reference_solver.py` is stronger:

1. Build separate `slmsuite` WGS seeds for x-target and y-target.
2. Initialize polarization phase layers from these seeds.
3. Fine-tune with composite objective:
   - target map matching,
   - crosstalk suppression,
   - ratio matching,
   - intended-channel efficiency,
   - phase smoothness regularization.

This yields a stronger practical reference.

## Metrics and score (0~1)

Core metrics:

- `match_x`, `match_y`, `mean_match`: cosine similarity to target maps.
- `separation_x`, `separation_y`, `separation`: how well each polarization stays in its own target ROIs.
- `own_efficiency`: fraction of power on intended channel targets.
- `ratio_mae_x`, `ratio_mae_y`, `mean_ratio_mae`: per-channel ratio errors.

Derived components:

- `ratio_score = exp(-mean_ratio_mae / score_ratio_scale)`
- `efficiency_score = min(1, own_efficiency / score_eff_target)`

Final score:

- `score = (separation^0.55) * (ratio_score^0.20) * (efficiency_score^0.25) * (mean_match^0.05)`

Interpretation:

- this score emphasizes **channel separation** and **useful in-channel power**,
- map similarity still matters, but is not the dominant term.

## Valid and better-than-baseline logic

Baseline is valid iff:

- `mean_match >= valid_match_min`
- `separation >= valid_separation_min`
- `score >= valid_score_min`

Reference is better iff:

- `reference_score >= baseline_score + better_score_margin`
- `reference_separation >= baseline_separation + better_sep_margin`

## Verification artifacts and their meaning

Saved under `verification/artifacts/`:

- `summary.json`
  - complete structured result (metrics, score, timing, pass/fail/comparison).
- `polarization_maps.png`
  - target/baseline/reference maps for x-input and y-input channels.
- `loss_and_metrics.png`
  - loss curves,
  - compact bar comparison (`match`, `separation`, `ratio_score`, `score`).

Quick diagnosis:

- high match but low separation: channel leakage problem,
- high separation but poor ratio_score: local energy split mismatch,
- low efficiency_score: not enough power in intended ROIs.

## Run verification

```bash
PY=python3
$PY benchmarks/Optics/holographic_polarization_multiplexing/verification/evaluate.py --device cpu
```

