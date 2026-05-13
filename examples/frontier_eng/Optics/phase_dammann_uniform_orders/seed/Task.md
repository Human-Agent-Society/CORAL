# Phase DOE P3 Contract: Dammann Uniform Orders

## Background
This is a **parameter optimization** task.
You optimize a 1D vector `transitions` (binary phase switching positions in one grating period), and evaluate a simulator output.

Think of it as:
- decision variable: `transitions` (continuous vector)
- simulator: `diffractio` propagation pipeline
- objective: make selected diffraction orders both uniform and efficient

## What You Need To Do
Improve how baseline chooses transition positions.

Primary optimization target:
- `baseline_transitions(problem)`

In practice, `solve_baseline(problem)` calls it, builds optical field, propagates, and evaluates order metrics.

## Editable Boundary
- Editable: `baseline/init.py`
- Read-only: `verification/validate.py`

Required API:
- `build_problem(config: dict | None) -> dict`
- `solve_baseline(problem: dict) -> dict`
- `build_incident_field(problem: dict, transitions: np.ndarray)`
- `evaluate_orders(problem: dict, intensity_x: np.ndarray, x: np.ndarray) -> dict`


### Input
`problem` contains:
- grating period, wavelength, focal distance, sampling settings
- target order range (`order_min` to `order_max`)

### Output of `solve_baseline(problem)`
A dict with:
- `transitions`: optimized transition vector
- `x_focus`: focus-plane x-grid
- `intensity_focus`: propagated intensity on focus line
- `metrics`: order statistics

## Baseline Implementation (current)
Baseline uses naive evenly-spaced transitions inside fixed margins, then:
1. build one-period binary phase mask
2. repeat period to build full grating
3. multiply lens phase
4. propagate with Rayleigh-Sommerfeld (`RS`)
5. integrate order-window energies

## Oracle Implementation
Verifier evaluates two stronger references and picks higher score:
1. literature transition table (from diffractio Dammann example)
2. SciPy differential evolution (`scipy.optimize.differential_evolution`)

Oracle is `best_of_literature_and_scipy_de`.

## Metrics and Score (Higher Is Better)
Raw metrics:
- `cv_orders` (lower better)
- `efficiency` (higher better)
- `min_to_max` (higher better)

Score:
- `uniform_score = clip(1 - cv_orders / 0.9, 0, 1)`
- `efficiency_score = clip((efficiency - 0.003) / (0.18 - 0.003), 0, 1)`
- `balance_score = clip((min_to_max - 0.15) / (0.90 - 0.15), 0, 1)`
- `score_pct = 100 * (0.60*uniform_score + 0.30*efficiency_score + 0.10*balance_score)`

Range: `0 ~ 100`, higher is better.

## Valid Criteria
- `cv_orders <= 0.8`
- `efficiency >= 0.003`
- `min_to_max >= 0.15`

## Practical Evolution Directions
- constrained continuous optimization over transitions
- symmetry-aware parameterization
- objective balancing between uniformity and efficiency
- spacing constraints for manufacturability

