# Phase DOE P4 Contract: Large-Scale Weighted Spot Array

## Background
This task is dense multi-target allocation:
- decision variable: phase map `(N, N)`
- forward model: Fourier propagation
- objective: satisfy weighted energy allocation over many spots (8x8)

Compared with Task01, this one has larger target count and broader distribution.

## What You Need To Do
Improve baseline phase generation so weighted spot-array quality increases.

Main function to optimize:
- `solve_baseline(problem)`

## Editable Boundary
- Editable: `baseline/init.py`
- Read-only: `verification/validate.py`

Required API:
- `build_problem(config: dict | None) -> dict`
- `solve_baseline(problem: dict) -> np.ndarray`
- `forward_intensity(problem: dict, phase: np.ndarray) -> np.ndarray`


### Input `problem`
- `x`, `y`: pixel coordinates
- `aperture_amp`: aperture mask `(N, N)`
- `spots`: 64 target spot coordinates
- `weights`: normalized target ratios
- `cfg`: SLM and grid settings

### Output
- `phase`: `(N, N)` phase map (radians)

## Baseline Implementation
Baseline currently uses direct non-iterative weighted superposition of plane-wave terms, then takes phase.

## Oracle Implementation
Verifier oracle uses iterative `slmsuite` WGS:
- `Hologram.optimize(method="WGS-Kim")`

## Metrics and Score (Higher Is Better)
Raw metrics:
- `ratio_mae`
- `cv_spots`
- `efficiency`

Score formula:
- `ratio_score = clip(1 - ratio_mae / 0.03, 0, 1)`
- `uniform_score = clip(1 - cv_spots / 1.40, 0, 1)`
- `efficiency_score = clip((efficiency - 0.40) / (0.90 - 0.40), 0, 1)`
- `score_pct = 100 * (0.45*ratio_score + 0.35*uniform_score + 0.20*efficiency_score)`

Range: `0 ~ 100`, higher is better.

## Valid Criteria
- `score_pct >= 20`
- `ratio_mae <= 0.03`
- `cv_spots <= 1.40`
- `efficiency >= 0.50`

## Practical Evolution Directions
- iterative weighted correction (instead of one-shot phase)
- local phase refinement / block updates
- adaptive balancing between ratio and efficiency

