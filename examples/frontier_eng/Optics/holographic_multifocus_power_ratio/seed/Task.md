# Holographic H1 Specification: Multifocus Power-Ratio Control

## Engineering background

You can think of this task as "image formation by a physical compiler":

- Input: one laser beam (a 2D field).
- Program: a small stack of trainable phase masks.
- Output: intensity pattern on a target plane.

Goal: produce **6 bright spots** at specified coordinates, and make their relative brightness follow a required ratio.

Why this matters in engineering:

- parallel laser machining (multiple processing points at once),
- optical tweezers (multiple trap sites),
- multi-channel optical coupling.

Economic relevance:

- better optical throughput and precision can increase yield and reduce process time.

## What you need to do

You are expected to improve the baseline optimization strategy so that the output is closer to the target under the task score.

The challenge setup is:

- editable target: `baseline/init.py`,
- evaluator and oracle are in `verification/` and should be treated as read-only.

## Core file/function to modify

Primary target:

- `baseline/init.py`
- Core function: `solve(spec, device=None, seed=0)`

You may also adjust helper functions in the same file, but keep return fields compatible with evaluator.

## Input contract (`spec`)

`verification/evaluate.py` builds `spec` from `make_default_spec()` and injects evaluation constants.

Important fields:

- `shape`: simulation grid size (e.g., 72 means 72x72 samples).
- `spacing`: physical sampling pitch (meters per pixel).
- `wavelength`: laser wavelength.
- `waist_radius`: Gaussian beam waist.
- `layer_z`: z positions of trainable phase layers.
- `output_z`: target observation plane.
- `focus_centers`: list of 6 target spot coordinates `(x, y)` in meters.
- `focus_ratios`: target relative power per spot.
- `roi_radius_m`: radius for measuring each spot power.

Scoring/verification constants added by evaluator:

- `score_eff_target`, `score_ratio_scale`,
- `valid_ratio_mae_max`, `valid_efficiency_min`, `valid_score_min`,
- `better_score_margin`, `better_shape_margin`.

## Output contract (from `solve`)

Your `solve` must return a dict containing at least:

- `system`: trained optical system (used by evaluator to propagate fields).
- `input_field`: source field.
- `target_field`: target field/intensity template.
- `loss_history`: list of training loss values.
- `spec` (recommended): merged runtime spec.

If these keys are missing or geometry mismatches, verification will fail.

## Baseline implementation (what it currently does)

Current baseline is intentionally simple:

1. Build Gaussian input field.
2. Build target field from 6 Gaussians weighted by target ratios.
3. Optimize phase layers with overlap-only objective:
   - `loss = 1 - |<output, target>|^2`
4. Use Adam for fixed steps.

Limitations by design:

- no direct ratio loss,
- no explicit leakage penalty,
- no curriculum/staged training.

## Oracle implementation (comparison reference)

`verification/reference_solver.py` is stronger and may use third-party tools:

1. Use `slmsuite` WGS to generate a high-quality phase seed.
2. Initialize optical layers from this seed.
3. Fine-tune with composite objective:
   - overlap term,
   - ratio error term,
   - leakage term,
   - phase smoothness regularizer.

This is intended as a stronger engineering reference, not a baseline.

## Metrics and score (0 to 1, higher is better)

Measured on output intensity:

- `ratio_mae`: mean absolute error of predicted focus ratios.
- `efficiency`: fraction of total energy inside all focus ROIs.
- `shape_cosine`: cosine similarity between normalized predicted and target intensity maps.

Derived:

- `ratio_score = exp(-ratio_mae / score_ratio_scale)`
- `efficiency_score = min(1, efficiency / score_eff_target)`

Final score:

- `score = (efficiency_score^0.58) * (ratio_score^0.22) * (shape_cosine^0.20)`

Interpretation:

- close to `1.0`: high efficiency, correct ratios, close target shape,
- around `0.2~0.4`: partially correct but significant deficits,
- near `0`: mostly failing objective.

## Valid and better-than-baseline logic

Baseline is `valid=True` iff all hold:

- `ratio_mae <= valid_ratio_mae_max`
- `efficiency >= valid_efficiency_min`
- `score >= valid_score_min`

Reference is `better_than_baseline=True` iff all hold:

- `reference_score >= baseline_score + better_score_margin`
- `reference_shape_cosine >= baseline_shape_cosine + better_shape_margin`

## Verification artifacts and how to read them

`verification/evaluate.py` writes to `verification/artifacts/`:

- `summary.json`:
  - machine-readable result summary,
  - includes spec, runtime, metrics, score, valid flag, and comparison verdict.
- `intensity_maps.png`:
  - side-by-side target vs baseline vs reference intensity maps,
  - quickest visual check for whether spots are at correct positions.
- `ratios_and_losses.png`:
  - bar chart of target/baseline/reference spot ratios,
  - training-loss curves for baseline/reference.

## Running verification

```bash
PY=python3
$PY benchmarks/Optics/holographic_multifocus_power_ratio/verification/evaluate.py --device cpu
```

Optional flags:

- `--seed`
- `--baseline-steps`
- `--reference-steps`
- `--artifacts-dir`

