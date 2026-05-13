# PyMOTO SIMP Compliance Task

## 1. Problem Statement

Design a material density field for a 2D load-bearing structure under a fixed volume-fraction budget.
The optimization objective is to minimize structural compliance while satisfying the material usage constraint.

## 2. Engineering Background

This is a classical topology optimization setting used in mechanical and structural engineering:

- lightweight design of brackets, cantilevers, and bridge-like members
- improved stiffness under given loads with limited material
- practical trade-off between structural performance and manufacturing cost

The task is aligned with density-based SIMP optimization workflows inspired by pyMOTO.

## 3. Design Variables

Let:

- `nelx = 50`
- `nely = 16`

The design variable is the flattened density vector:

```text
density_vector in R^(nelx * nely) = R^800
```

Each element density is clipped by evaluator into:

```text
[rho_min, 1.0], rho_min = 1e-9
```

## 4. Physical Model and Setup

The evaluator uses an independent finite-element pipeline:

1. Build 2D voxel/element domain
2. Apply fixed boundary conditions on left edge DOFs
3. Apply a point load at the right-middle node (y-direction)
4. Apply SIMP interpolation:

```text
E(x) = Emin + (E0 - Emin) * x^penal
```

5. Assemble stiffness matrix and solve linear system
6. Compute compliance:

```text
c = F^T u
```

Configuration source: `references/problem_config.json`.

## 5. Objective and Constraint

### Objective

Minimize compliance `c`.

### Constraint

Material usage constraint:

```text
mean(density) <= volfrac
```

with evaluator feasibility tolerance.

## 6. Candidate Program Contract

Candidate file: `scripts/init.py`

The candidate must output `temp/submission.json` containing at least:

- `density_vector`

The evaluator does not trust candidate-reported score fields; it recomputes compliance independently.

## 7. What Agents May Optimize

Inside `scripts/init.py`, agents may optimize strategy-level behavior, for example:

- density update policy
- filter choice/usage within allowed scope
- step-size or iteration schedule
- OC update strategy and schedule

Core evaluator interfaces and benchmark metadata are read-only by task constraints.

## 8. Evaluation Workflow

Given a candidate program path:

1. execute candidate script
2. read `temp/submission.json`
3. validate shape and numeric sanity of `density_vector`
4. compute independent compliance and feasibility
5. report metrics (`combined_score`, `valid`, diagnostics)

## 9. Score Definition

If feasible:

```text
combined_score = baseline_uniform_compliance / compliance
```

Else:

```text
combined_score = 0
valid = 0
```

This makes higher score better while preserving compliance-minimization behavior.

## 10. References

- pyMOTO repository and official topology optimization examples
- SIMP-based compliance minimization literature

