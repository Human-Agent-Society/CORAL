# Dawn Aircraft Design Optimization (DawnAircraftDesignOptimization)

## 1. Background

Conceptual aircraft sizing is a coupled engineering optimization problem. Mission targets (payload, cruise altitude, endurance) interact with aerodynamic, structural, and propulsion decisions. This benchmark captures that coupling with a simplified but constrained model.

This task is inspired by the design optimization flow from:
- `https://github.com/peterdsharpe/DawnDesignTool`
- original reference script: `design_opt.py`

## 2. Task

Given a fixed mission profile, select aircraft design variables to minimize total aircraft mass while satisfying all feasibility constraints.

Mission inputs are fixed by `references/mission_config.json`:

- payload mass
- cruise altitude
- endurance duration

## 3. Decision Variables

The submission contains 7 continuous variables:

- `wing_span_m`
- `wing_area_m2`
- `fuselage_length_m`
- `fuselage_diameter_m`
- `motor_power_kw`
- `battery_mass_kg`
- `cruise_speed_mps`

Bounds are enforced by `references/mission_config.json`.

## 4. Physics and Performance Model

The evaluator computes a simplified conceptual model including:

- standard-atmosphere density at cruise altitude
- mass breakdown (wing, fuselage, tail, landing gear, propulsion, systems)
- cruise lift/drag and required cruise power
- stall speed and takeoff distance estimate
- structural root stress estimate
- battery usable energy vs required mission energy
- wing loading and geometric ratios

## 5. Constraints

A design is feasible only if all margins are non-negative:

- aspect-ratio lower/upper bounds
- fuselage fineness lower bound
- takeoff distance upper bound
- stall speed upper bound
- cruise lift capability
- allowable structural root stress
- endurance energy requirement
- cruise power headroom
- wing loading upper bound

## 6. Objective and Score

### Objective

Minimize `total_mass_kg` under feasibility constraints.

### Returned metrics

- `total_mass_kg`
- `cruise_power_kw`
- `takeoff_distance_m`
- `stall_speed_mps`
- `aspect_ratio`
- `feasible`
- `valid`
- `combined_score`

### Combined score

If feasible:

```text
combined_score = mass_reference_kg / (mass_reference_kg + total_mass_kg)
```

If infeasible:

```text
combined_score = 0
valid = 0
```

## 7. Input / Output Contract

### Input to candidate

Candidate script runs as:

```bash
python scripts/init.py
```

It can read mission/config data from:

- `references/mission_config.json`

### Required output

Candidate must write `submission.json` with all 7 numeric keys.

Missing keys, non-numeric values, non-finite values, or out-of-bound values are invalid.

## 8. Evaluation Commands

Run evaluator on candidate script:

```bash
python verification/evaluator.py scripts/init.py
```

Run evaluator on an existing submission:

```bash
python verification/evaluator.py --submission submission.json
```

Run with framework integration:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=Aerodynamics/DawnAircraftDesignOptimization \
  task.runtime.use_conda_run=false \
  algorithm.iterations=0
```

## 9. Baseline

Baseline candidate is `scripts/init.py` (also copied to `baseline/solution.py`):

- read-only physics and constraints
- editable `solve_design()`
- baseline strategy: multi-start local search with finite-difference gradient step and penalty handling
