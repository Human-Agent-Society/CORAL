# Dawn Aircraft Design Optimization

Design a conceptual fixed-wing aircraft for a given mission profile by tuning wing, fuselage, propulsion, and battery parameters.

The benchmark is inspired by the optimization workflow in `DawnDesignTool/design_opt.py`, but simplified into a single-file evolvable candidate plus an independent evaluator.

## Files

- `Task.md`: full task statement and scoring rules
- `references/mission_config.json`: mission targets, bounds, constants, and constraints
- `scripts/init.py`: evolvable baseline candidate (`solve_design()` is the editable core)
- `verification/evaluator.py`: independent evaluator
- `verification/requirements.txt`: runtime dependencies
- `baseline/solution.py`: baseline copy of `scripts/init.py`
- `frontier_eval/`: unified metadata for framework integration

## Quick Start

### 1. Install dependencies

```bash
pip install -r verification/requirements.txt
```

### 2. Run baseline candidate

```bash
cd benchmarks/Aerodynamics/DawnAircraftDesignOptimization
python scripts/init.py
# output: submission.json
```

### 3. Evaluate a candidate program directly

```bash
cd benchmarks/Aerodynamics/DawnAircraftDesignOptimization
python verification/evaluator.py scripts/init.py
```

### 4. Evaluate an existing submission file

```bash
cd benchmarks/Aerodynamics/DawnAircraftDesignOptimization
python verification/evaluator.py --submission submission.json
```

### 5. Run with frontier_eval (unified)

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=Aerodynamics/DawnAircraftDesignOptimization \
  task.runtime.use_conda_run=false \
  algorithm.iterations=0
```

Equivalent named-task config:

```bash
python -m frontier_eval task=dawn_aircraft_design_optimization algorithm.iterations=0
```

## Submission Format

Write `submission.json` as a JSON object containing these numeric fields:

```json
{
  "wing_span_m": 26.0,
  "wing_area_m2": 24.0,
  "fuselage_length_m": 9.0,
  "fuselage_diameter_m": 0.9,
  "motor_power_kw": 45.0,
  "battery_mass_kg": 170.0,
  "cruise_speed_mps": 27.0
}
```

All required fields and bounds are defined in `references/mission_config.json`.

## Scoring Summary

- Primary objective: minimize `total_mass_kg`
- Feasibility: all constraints must be satisfied (takeoff, lift, stress, endurance energy, power headroom, wing loading, fuselage fineness, aspect ratio)
- Score:
  - feasible: `combined_score = mass_reference_kg / (mass_reference_kg + total_mass_kg)`
  - infeasible: `combined_score = 0`, `valid = 0`

## Editable Boundary

The evolvable file is `scripts/init.py`.

- Keep the `EVOLVE-BLOCK-START` and `EVOLVE-BLOCK-END` markers unchanged.
- Treat physics model, constraint definitions, and output contract as read-only.
- Modify `solve_design()` to explore better search or optimization strategies.

