# ISCSO 2015 — 45-Bar 2D Truss Size + Shape Optimization

## Problem

Minimize weight of 2D planar truss structure:
- **Structure**: 20 nodes, 45 members, span 20 m (20000 mm)
- **Design variables**: 54 total
  - 45 area variables: `A_1, A_2, ..., A_45` (one per member)
  - 9 shape variables: `y_2, y_4, y_6, y_8, y_10, y_12, y_14, y_16, y_18` (y-coordinates of top-chord nodes)
- **Load case**: Single load case with 3 vertical forces
  - Node 15: 60 kips (266.9 kN) downward
  - Node 17: 80 kips (355.9 kN) downward
  - Node 19: 60 kips (266.9 kN) downward
- **Constraints**: 
  - Stress: `|σ_i| ≤ 30 ksi` (206.8 MPa) for all members
  - Displacement: `|δ_j| ≤ 2.0 in` (50.8 mm) for all free DOFs
- **Evaluation limit**: Maximum 7,000 FEM evaluations

## Parameters

### Material Properties
- **Elastic modulus**: E = 30,000 ksi = 206.8 GPa
- **Density**: ρ = 0.283 lb/in³ = 7.86e-6 kg/mm³

### Constraints
- **Stress limit**: 30 ksi = 206.8 MPa (tension and compression)
- **Displacement limit**: ±2.0 in = ±50.8 mm (horizontal and vertical)

### Supports
- **Node 1**: Pinned support (fixes x and y displacements, left end)
- **Node 20**: Roller support (fixes y displacement only, right end)

### Node Numbering
- Nodes 1-20: Sequential numbering
- **Bottom chord**: Nodes 1, 3, 5, 7, 9, 11, 13, 15, 17, 19 (odd numbers)
- **Top chord**: Nodes 2, 4, 6, 8, 10, 12, 14, 16, 18 (even numbers, shape variables)

### Variable Bounds
- **Area variables** (`A_1` to `A_45`):
  - Range: 0.1 to 15.0 in² (64.5 to 9677 mm²)
  - Discrete values: `{0.1, 0.2, 0.3, ..., 14.9, 15.0}` in²
  - Step size: 0.1 in² (64.5 mm²)
- **Shape variables** (`y_2, y_4, ..., y_18`):
  - Range: 100 to 1400 in (2540 to 35560 mm)
  - Discrete integers: `{100, 101, 102, ..., 1399, 1400}` in
  - Step size: 1 in (25.4 mm)

## Design Variables

The solution vector has 54 elements in this order:
```
x = [A_1, A_2, ..., A_45, y_2, y_4, y_6, y_8, y_10, y_12, y_14, y_16, y_18]
```

- **First 45 elements**: Cross-sectional areas for members 1-45
  - `A_i ∈ {0.1, 0.2, ..., 15.0}` in² (discrete, step 0.1 in²)
- **Last 9 elements**: y-coordinates for top-chord nodes 2, 4, 6, 8, 10, 12, 14, 16, 18
  - `y_j ∈ {100, 101, ..., 1400}` in (discrete integers)

**Important**: The optimization must start from a **random initial point** in the design space.

## Objective Function

Minimize structural weight:
```
W(x) = Σ (ρ * L_i(x) * A_i)
```

where:
- `ρ = 0.283 lb/in³` = 7.86e-6 kg/mm³ (material density)
- `L_i(x)` = length of member i (depends on shape variables)
- `A_i` = cross-sectional area of member i
- Sum is over all 45 members

## Constraints

For the single load case, all constraints must be satisfied:

1. **Stress constraints** (all 45 members):
   ```
   |σ_i| ≤ 30 ksi = 206.8 MPa
   ```
   where `σ_i` is the axial stress in member i (positive = tension, negative = compression)

2. **Displacement constraints** (all free DOFs):
   ```
   |δ_j| ≤ 2.0 in = 50.8 mm
   ```
   where `δ_j` is the displacement at free degree of freedom j

A solution is **feasible** only if all constraints are satisfied (within tolerance 1e-6).

## Submission Format

Output a JSON file at `temp/submission.json`:

```json
{
  "benchmark_id": "iscso_2015",
  "solution_vector": [A_1, A_2, ..., A_45, y_2, y_4, y_6, y_8, y_10, y_12, y_14, y_16, y_18],
  "algorithm": "<your_algorithm_name>",
  "num_evaluations": <number_of_fem_evaluations_used>
}
```

**Requirements**:
- `solution_vector`: Array of 54 numbers (45 areas + 9 shape coordinates)
- `algorithm`: String describing your optimization method
- `num_evaluations`: Integer ≤ 7,000 (number of times FEM was called)

**Note**: The evaluator independently tracks and validates the evaluation count limit.

## Scoring

- **Feasible solution**: Score = structural weight (kg), **lower is better**
- **Infeasible solution**: Score = +∞

The final design must be feasible (no constraint violations allowed).

## References

- Problem data: `references/problem_data.json`
- Evaluator: `verification/evaluator.py`
- FEM solver: `verification/fem_truss2d.py`
