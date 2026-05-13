# Task: Real-Case Thermal Control from differentiable-simulation-am

## 1. Background

The upstream project `differentiable-simulation-am` studies additive-manufacturing process optimization with differentiable simulation. Its public repository contains a real build geometry (`0.k`), a real toolpath (`toolpath.crs`), and a Taichi-based differentiable thermal workflow.

This task adapts that real published build case into Frontier-Engineering.

## 2. Source Fidelity

This benchmark uses the original committed upstream files:

- `references/original/0.k`
- `references/original/toolpath.crs`

However, the upstream notebook also loads:

- `data/target.npy`
- `data/target_q.npy`

Those target files are referenced in the notebook but are not published in the repository. Therefore, this benchmark preserves the real geometry/toolpath/material constants from upstream and defines a reproducible thermal-control objective on top of the real published case.

## 3. Goal

For each selected real layer window extracted from the upstream toolpath, optimize a normalized laser-power control vector to minimize thermal-control loss.

The candidate parameter vector is a low-dimensional knot representation of the power trajectory:

```text
params = [p_1, p_2, ..., p_k],  with 0 <= p_i <= 1
```

These knots are linearly interpolated into a full per-step power schedule over the real layer trajectory.

## 4. Editable Scope

Only modify the optimization logic inside `scripts/init.py` between:

```python
# EVOLVE-BLOCK-START
...
# EVOLVE-BLOCK-END
```

The following signatures must remain unchanged:

```python
def load_cases(case_file=None):
    ...

def simulate(params, case):
    ...

def baseline_solve(case, max_sim_calls=..., simulate_fn=...):
    ...

def solve(case, max_sim_calls=..., simulate_fn=...):
    ...
```

## 5. Real Benchmark Cases

The current benchmark evaluates 4 real cases derived from actual layers of the upstream toolpath:

- `toolpath_layer_01`
- `toolpath_layer_02`
- `toolpath_layer_27`
- `toolpath_layer_28`

Each case uses:

- real `(x, y, z)` path coordinates,
- real scan timing,
- real layer identity,
- a short cooling tail appended after the active path segment.

## 6. Process Constants

The benchmark keeps the main constants used by the upstream notebook, including:

- `ambient = 300.0`
- `q_in = 250.0`
- `r_beam = 1.0`
- `h_conv = 0.00005`
- `h_rad = 0.2`
- `solidus = 1533.15`
- `liquidus = 1609.15`

## 7. Surrogate Thermal Rollout

Given the real toolpath window and the candidate power schedule, the benchmark rolls out a temperature proxy over time.

The thermal state depends on:

- thermal memory,
- normalized laser power,
- actual scan speed,
- path turning intensity,
- real laser on/off state from the upstream toolpath.

This preserves the real case geometry and process timing while making the evaluator lightweight and reproducible.

## 8. Objective

The loss combines:

1. tracking a target thermal profile,
2. underheat penalty below the solidus temperature,
3. overheat penalty above the liquidus temperature,
4. smoothness penalty on power evolution,
5. energy regularization toward a nominal operating level.

The target thermal profile is derived from the real layer path geometry and process timing so that all benchmark cases remain deterministic and reproducible.

## 9. Constraints

The candidate must satisfy:

1. each control knot must remain in `[0, 1]`,
2. adjacent knot changes are projected using a ramp limit,
3. the required function signatures must remain unchanged.

## 10. Evaluation Pipeline

For each case, the evaluator:

1. loads the real case metadata,
2. constructs the layer window from the original toolpath,
3. runs the canonical baseline,
4. runs the candidate solver,
5. evaluates the returned parameters with the same simulator,
6. reports candidate vs baseline loss and simulation-call cost.

## 11. Score

The evaluator reports:

- `combined_score`
- `valid`
- `mean_candidate_loss`
- `mean_baseline_loss`
- `mean_improvement_ratio`
- `total_candidate_sim_calls`

A valid run must satisfy the parameter constraints. Lower loss and fewer evaluation calls are better.

## 12. Commands

From the task directory:

```bash
python verification/evaluator.py scripts/init.py
python verification/evaluator.py baseline/solution.py
```

From repository root:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=AdditiveManufacturing/DiffSimThermalControl \
  task.runtime.conda_env=<your_env> \
  algorithm.iterations=0
```

For the local environment prepared in this work, use `task.runtime.conda_env=Engi`.


