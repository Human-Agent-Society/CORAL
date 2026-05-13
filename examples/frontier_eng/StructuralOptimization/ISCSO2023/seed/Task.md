# ISCSO 2023 — 284-Member 3D Truss Sizing Optimization

## Problem

Minimize weight of 3D tower truss structure:
- **Structure**: 92 nodes, 284 members, 23 levels (4 nodes per level)
- **Design variables**: 284 discrete section IDs
  - One variable per member: `S_0, S_1, ..., S_283`
  - Each `S_i ∈ {1, 2, ..., 37}` represents a section ID from the database
- **Load cases**: 3 independent load cases
  - **LC 0**: 12 kN total in +X direction, distributed equally to all unsupported nodes (88 nodes, ~136.36 N per node)
  - **LC 1**: 12 kN total in +Y direction, distributed equally to all unsupported nodes (88 nodes, ~136.36 N per node)
  - **LC 2**: 15 kN total in -Z direction, distributed equally to all unsupported nodes (88 nodes, ~170.45 N per node)
- **Constraints**:
  - Stress: `|σ_i| ≤ 248.2 MPa` for all members (all load cases)
  - Displacement: `|δ_j| ≤ 5.0 mm` for all free DOFs (all load cases)
- **Evaluation limit**: Maximum 200,000 FEM evaluations

## Parameters

### Material Properties
- **Elastic modulus**: E = 200 GPa = 200,000 MPa
- **Density**: ρ = 7.85e-3 kg/mm³
- **Yield stress**: 248.2 MPa (used as stress limit)

### Constraints
- **Stress limit**: 248.2 MPa (tension and compression, AISC-LRFD 1994)
- **Displacement limit**: 5.0 mm (all directions: x, y, z)

### Tower Geometry
- **Levels**: 23 levels (level 0 to level 22)
- **Height**: 40 m = 40,000 mm
- **Bottom cross-section**: Square, half-width 2 m = 2000 mm
- **Top cross-section**: Square, half-width 0.5 m = 500 mm
- **Node arrangement**: At each level i (0-22), 4 nodes form a square
  - Node 4i: (+hw, +hw, z)
  - Node 4i+1: (-hw, +hw, z)
  - Node 4i+2: (-hw, -hw, z)
  - Node 4i+3: (+hw, -hw, z)
  - where hw = 2000 - i × (2000-500)/22

### Supports
- **4 base nodes**: Nodes 0, 1, 2, 3 (level 0, bottom)
- **All supports**: Fully fixed (fix_x = true, fix_y = true, fix_z = true)
- **Unsupported nodes**: 88 nodes (nodes 4-91)

### Section Database
- **37 pipe sections**: IDs 1 through 37
- **Area range**: 161.29 mm² (ID 1) to 13741.91 mm² (ID 37)
- **Discrete selection**: Each member must use one of the 37 available sections
- **Section data**: Available in `references/problem_data.json` under `"sections"` array

## Design Variables

The solution vector has 284 elements:
```
x = [S_0, S_1, S_2, ..., S_283]
```

where:
- `S_i` = section ID for member i (i = 0, 1, ..., 283)
- `S_i ∈ {1, 2, 3, ..., 37}` (integer values only)
- Each ID corresponds to a specific pipe section with a fixed cross-sectional area

**Important**: The optimization must start from a **random initial point** in the design space.

## Objective Function

Minimize structural weight:
```
W(x) = Σ (ρ * L_i * A(S_i))
```

where:
- `ρ = 7.85e-3 kg/mm³` (material density)
- `L_i` = length of member i (fixed, depends on tower geometry)
- `A(S_i)` = cross-sectional area of section ID `S_i` (from database)
- Sum is over all 284 members

## Constraints

For **each of the 3 load cases**, all constraints must be satisfied:

1. **Stress constraints** (all 284 members):
   ```
   |σ_i| ≤ 248.2 MPa
   ```
   where `σ_i` is the axial stress in member i under the current load case
   - Positive = tension, negative = compression
   - Checked against AISC-LRFD 1994 regulations

2. **Displacement constraints** (all free DOFs):
   ```
   |δ_j| ≤ 5.0 mm
   ```
   where `δ_j` is the displacement at free degree of freedom j (x, y, or z direction)

A solution is **feasible** only if all constraints are satisfied for **all 3 load cases** (within tolerance 1e-6).

## Submission Format

Output a JSON file at `temp/submission.json`:

```json
{
  "benchmark_id": "iscso_2023",
  "solution_vector": [S_0, S_1, S_2, ..., S_283],
  "algorithm": "<your_algorithm_name>",
  "num_evaluations": <number_of_fem_evaluations_used>
}
```

**Requirements**:
- `solution_vector`: Array of 284 integers (section IDs 1-37)
- `algorithm`: String describing your optimization method
- `num_evaluations`: Integer ≤ 200,000 (number of times FEM was called)

**Note**: The evaluator independently tracks and validates the evaluation count limit.

## Scoring

- **Feasible solution**: Score = structural weight (kg), **lower is better**
- **Infeasible solution**: Score = +∞

The final design must be feasible (no constraint violations allowed for any load case).

## References

- Problem data: `references/problem_data.json`
- Evaluator: `verification/evaluator.py`
- FEM solver: `verification/fem_truss3d.py`
