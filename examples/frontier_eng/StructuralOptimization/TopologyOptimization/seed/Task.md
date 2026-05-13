# Topology Optimization

## 1. Problem

Optimize the density field of a 2D MBB beam under a fixed material budget.
The goal is to produce a lightweight yet stiff structure by minimizing compliance subject to a volume fraction constraint.

## 2. Design Variables

Let:

- `nelx = 60`
- `nely = 20`

The solution is a density field with:

```text
60 * 20 = 1200
```

element densities.

The submission stores these as a flattened array:

```text
density_vector
```

which the evaluator reshapes into a `(nely, nelx)` field.

## 3. Physical Model

The evaluator uses:

- 2D quadrilateral finite elements (Q4)
- plane-stress constitutive model
- SIMP material interpolation
- MBB half-beam boundary conditions

Material and optimization parameters from `references/problem_config.json`:

- `volfrac = 0.5`
- `penal = 3.0`
- `rmin = 1.5`
- `E0 = 1.0`
- `Emin = 1e-9`
- `nu = 0.3`

A downward force is applied at the top-left node.

## 4. Objective

Minimize structural compliance:

```text
c = F^T u
```

Lower compliance means a stiffer design and a better score.

## 5. Constraint

The mean density must satisfy:

```text
mean(density) <= volfrac
```

The evaluator clips each density into `[1e-3, 1.0]` before analysis.

## 6. Submission Format

Your program must write `temp/submission.json` with the following structure:

```json
{
  "benchmark_id": "topology_optimization",
  "density_vector": [0.5, 0.5, 0.5],
  "nelx": 60,
  "nely": 20
}
```

Requirements:

- `density_vector` length must equal `nelx * nely = 1200`
- all entries must be finite numeric values
- output format must remain unchanged

## 7. Feasibility Rules

A submission is infeasible if:

1. `submission.json` is missing
2. `density_vector` is missing
3. the vector length is incorrect
4. the vector contains `NaN` or `Inf`
5. the FEM solve fails
6. the mean density exceeds the volume limit

## 8. Evaluation Workflow

The verification script:

1. runs the candidate program in a temporary working directory
2. loads `temp/submission.json`
3. validates the density vector
4. solves the independent FEM system
5. computes compliance and volume fraction
6. returns feasibility and score

Run:

```bash
python verification/evaluator.py scripts/init.py
```

## 9. Scoring

- **Feasible**: score = compliance, lower is better
- **Infeasible**: invalid result
- In `frontier_eval`, feasible solutions use `combined_score = -compliance`

## 10. References

- Problem config: `references/problem_config.json`
- Baseline solver: `scripts/init.py`
- Evaluator: `verification/evaluator.py`
