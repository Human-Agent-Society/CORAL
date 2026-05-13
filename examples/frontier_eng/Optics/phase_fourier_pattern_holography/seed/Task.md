# Phase DOE P2 Contract: Hard Fourier Pattern Holography

## Background
This task is image reconstruction under constraints:
- Decision variable: phase map `phase[y, x]`
- Forward model: FFT-based propagation to intensity image
- Objective: match a sparse high-contrast target while keeping dark zones dark

Equivalent CS view: constrained inverse problem / non-convex optimization on a 2D field.

## What You Need To Do
Improve `baseline/init.py` so the reconstructed intensity image better fits target structure and suppresses leakage in designated dark regions.

Primary function to optimize:
- `solve_baseline(problem, seed=None)`

## Editable Boundary
- Editable: `baseline/init.py`
- Read-only: `verification/validate.py`

Required API:
- `build_problem(config: dict | None) -> dict`
- `solve_baseline(problem: dict, seed: int | None = None) -> np.ndarray`
- `forward_intensity(problem: dict, phase: np.ndarray) -> np.ndarray`


### Input `problem`
Key fields:
- `x`, `y`: pixel coordinates
- `aperture_amp`: aperture mask `(N, N)`
- `target_amp`: target amplitude map `(N, N)`
- `cfg`: includes `slm_pixels`, `seed`, etc.

### Output
- phase map `phase` with shape `(N, N)` (radians)

## Core Function to Modify
Main modification point:
- `solve_baseline(problem, seed=None)`

The verifier always calls this function, then evaluates metrics on the produced intensity.

## Baseline Implementation (current)
Baseline is one-shot and non-iterative:
1. attach random phase to target amplitude
2. inverse FFT once
3. use resulting phase as hologram

Fast but weak for difficult sparse/high-contrast structures.

## Oracle Implementation
Oracle uses iterative weighted GS in `slmsuite`:
- `Hologram.optimize(method="WGS-Kim")`
- iterative amplitude/phase correction

This usually improves structure fidelity and dark-zone control.

## Metrics and Score (Higher Is Better)
Verifier computes:
- `nmse`: normalized RMSE between predicted intensity and target intensity
- `energy_in_target`: energy fraction where `target_amp > 0.30`
- `dark_suppression`: `1 - leak`, where leak is energy fraction in `target_amp < 0.03`

Score formula:
- `pattern_score = clip(1 - nmse / 4.0, 0, 1)`
- `energy_score = clip((energy_in_target - 0.10) / (0.70 - 0.10), 0, 1)`
- `dark_score = clip((dark_suppression - 0.35) / (0.90 - 0.35), 0, 1)`
- `score_pct = 100 * (0.55*pattern_score + 0.30*energy_score + 0.15*dark_score)`

Range: `0 ~ 100` (higher is better).

## Valid Criteria
Baseline is valid if:
- `score_pct >= 20`
- `energy_in_target >= 0.45`
- `dark_suppression >= 0.60`

## Expected Optimization Space
Typical high-impact improvements:
- iterative phase retrieval instead of one-shot inverse
- target-aware weighting for sparse structures
- strategies to penalize leakage in dark areas
- better initialization and iteration scheduling

