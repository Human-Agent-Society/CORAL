# Phase DOE P1 Contract: Hard Weighted Multi-Spot

## Background
You can view this task as a **2D optimization problem**:
- Input: a phase map `phase[y, x]`
- Black-box forward model: `phase -> far-field intensity`
- Goal: make many target spots receive desired relative energy

In optics terms, this is phase-only Fourier holography. In ML/optimization terms, this is a non-convex objective over a 2D array.

## What You Need To Do
Improve the baseline in `baseline/init.py` so that the generated phase map achieves better weighted spot distribution.

Recommended modification point:
- `solve_baseline(problem)`

You can also add helper functions in the same file, but keep the public API unchanged.

## Editable Boundary
- Editable: `baseline/init.py`
- Read-only (evaluation logic): `verification/validate.py`

Required API that verifier imports:
- `build_problem(config: dict | None) -> dict`
- `solve_baseline(problem: dict) -> np.ndarray`
- `forward_intensity(problem: dict, phase: np.ndarray) -> np.ndarray`


### Input to `solve_baseline(problem)`
`problem` is a dict built by `build_problem`, with key fields:
- `x`, `y`: 1D pixel coordinates (`np.arange(N)`)
- `aperture_amp`: aperture mask, shape `(N, N)`
- `spots`: target spot coordinates, shape `(K, 2)`
- `weights`: normalized target ratios, shape `(K,)`
- `cfg`: config dict (`slm_pixels`, grid sizes, etc.)

### Output from `solve_baseline(problem)`
- `phase`: float array of shape `(N, N)`
- Interpreted as phase in radians for each SLM pixel

## Core Function to Modify
Primary function:
- `solve_baseline(problem)`

Verifier flow:
1. call your `solve_baseline`
2. call `forward_intensity(problem, phase)`
3. compute metrics and score
4. compare with oracle

## Baseline Implementation (current)
Baseline is intentionally simple:
1. For each target spot, create one plane-wave term in complex field
2. Weighted coherent sum over all spots
3. Use angle of summed field as phase map

This is fast and deterministic but not iterative, so dense non-uniform targets are hard.

## Oracle Implementation
Oracle in verifier uses `slmsuite` weighted Gerchberg-Saxton:
- `Hologram.optimize(method="WGS-Kim")`
- Iteratively updates hologram to better match target energy distribution

So oracle is a stronger iterative solver; baseline is non-iterative.

## Metrics and Score (Higher Is Better)
Verifier computes:
- `ratio_mae`: mean absolute error between achieved spot ratios and target ratios (lower better)
- `cv_spots`: coefficient of variation of per-spot energy (lower better)
- `efficiency`: fraction of total energy captured by target windows (higher better)
- `min_peak_ratio`: weakest target peak / strongest target peak (higher better)

Then:
- `ratio_score = clip(1 - ratio_mae / 0.07, 0, 1)`
- `uniform_score = 1 / (1 + (cv_spots / 0.85)^2)`
- `efficiency_score = clip((efficiency - 0.15) / (0.80 - 0.15), 0, 1)`
- `peak_score = clip((min_peak_ratio - 0.003) / (0.20 - 0.003), 0, 1)`
- `score = 0.25*ratio_score + 0.45*uniform_score + 0.20*efficiency_score + 0.10*peak_score`
- `score_pct = 100 * score` (compatibility field)

Range: `0 ~ 1` (higher is better).

## Valid Criteria
Baseline is valid if all true:
- `score >= 0.20`
- `efficiency >= 0.45`
- `min_peak_ratio > 0`

## Expected Optimization Space
Typical improvements that work:
- iterative phase retrieval (GS/WGS variants)
- per-spot feedback correction
- regularization or damping for stability
- better initialization than direct superposition
