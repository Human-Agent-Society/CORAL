# Holographic H2 Specification: Multi-Plane Focusing

## Engineering background

Task 1 is single-plane focusing. Task 2 adds **depth**.

You now need one optical stack that works at multiple distances `z`:

- same hardware parameters,
- different desired patterns on different output planes.

Think of it as one model serving multiple views/slices, where each depth has its own target ratio.

Typical applications:

- 3D optical trapping,
- volumetric laser processing,
- depth-multiplexed projection.

Economic value:

- one optical component serving multiple depth functions reduces system complexity and calibration cost.

## What you need to do

Improve optimization in baseline so that all planes are satisfied better under the task score.

Editable area:

- `baseline/init.py`

Read-only for challenge use:

- `verification/evaluate.py`
- `verification/reference_solver.py`

## Core file/function to modify

Main function:

- `baseline/init.py`
- `solve(spec, device=None, seed=0)`

Keep output structure compatible with evaluator.

## Input contract (`spec`)

Main fields:

- global optical setup:
  - `shape`, `spacing`, `wavelength`, `waist_radius`, `layer_z`
- `planes`: list of plane configs. Each plane has:
  - `z`: output plane depth,
  - `centers`: target focus coordinates,
  - `ratios`: target power split among focuses on that plane.
- `roi_radius_m`: ROI radius to measure focus powers.

Evaluator also injects:

- score constants: `score_eff_target`, `score_ratio_scale`,
- validity thresholds,
- reference comparison margins.

## Output contract (from `solve`)

Required keys:

- `system`
- `input_field`
- `target_fields` (one per plane)
- `loss_history`
- `spec` (recommended)

Evaluator uses `system.measure_at_z(input_field, z=plane_z)` for each plane.

## Baseline implementation (current)

Current baseline is intentionally weak:

1. Build one input Gaussian field.
2. Build one target field per plane.
3. Compute overlap loss on each plane.
4. Average plane losses and optimize with Adam.

What it misses:

- no explicit ratio objective,
- no explicit leakage/efficiency control,
- no adaptive weighting for hard planes.

## Oracle implementation (current)

`verification/reference_solver.py` is stronger:

1. Run `slmsuite` WGS per plane to generate phase seeds.
2. Fuse seeds into multi-layer initialization.
3. Fine-tune with composite objective per plane:
   - overlap,
   - ratio error,
   - leakage.
4. Reweight harder planes dynamically during training.

This is a stronger engineering baseline for comparison.

## Metrics and score (0~1)

For each plane `m`:

- `ratio_mae_m`
- `efficiency_m = P_focus_m / P_total_m`
- `shape_cosine_m = cosine(I_pred_norm_m, I_target_norm_m)`

Derived per-plane components:

- `ratio_score_m = exp(-ratio_mae_m / score_ratio_scale)`
- `efficiency_score_m = min(1, efficiency_m / score_eff_target)`

Per-plane score:

- `score_m = (efficiency_score_m^0.50) * (ratio_score_m^0.35) * (shape_cosine_m^0.15)`

Global metrics:

- `mean_ratio_mae`
- `mean_efficiency`
- `mean_shape_cosine`
- `mean_score = average(score_m)`

Interpretation:

- score near `1`: high efficiency + accurate ratios + close target maps across planes,
- score near `0`: failing on one or more planes severely.

## Valid and better-than-baseline logic

Baseline `valid=True` iff:

- `mean_ratio_mae <= valid_mean_ratio_mae_max`
- `mean_efficiency >= valid_mean_efficiency_min`
- `mean_score >= valid_mean_score_min`

Reference `better_than_baseline=True` iff:

- `reference_mean_score >= baseline_mean_score + better_score_margin`
- `reference_mean_shape_cosine >= baseline_mean_shape_cosine + better_shape_margin`

## Verification artifacts and how to read them

Generated under `verification/artifacts/`:

- `summary.json`
  - full metrics/spec/timing + pass/fail/comparison flags.
- `plane_intensity_maps.png`
  - for each plane: target / baseline / reference intensity maps.
- `loss_and_efficiency.png`
  - loss curves + per-plane efficiency bars.

How to debug quickly:

- if ratio is wrong but spot positions are right: improve ratio-specific terms,
- if efficiency is low everywhere: improve leakage/energy concentration objective,
- if only one plane fails: use plane-aware weighting/curriculum.

## Run verification

```bash
PY=python3
$PY benchmarks/Optics/holographic_multiplane_focusing/verification/evaluate.py --device cpu
```

