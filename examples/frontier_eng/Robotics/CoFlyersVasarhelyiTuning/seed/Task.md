# Task: CoFlyers Vasarhelyi Parameter Tuning

## Overview

This task asks the agent to tune `Vasarhelyi` flocking parameters on the publicly released CoFlyers cases.

Each case provides a set of original `baseline_params`. The candidate is allowed to modify only the released Vasarhelyi tuning parameters while keeping the controller structure fixed.

## Tunable Parameters

- `r_rep_0`
- `p_rep`
- `r_frict_0`
- `c_frict`
- `v_frict`
- `p_frict`
- `a_frict`
- `r_shill_0`
- `v_shill`
- `p_shill`
- `a_shill`

## Background and Provenance

`CoFlyers` is a platform for evaluating and verifying cooperative drone-swarm motion algorithms and models. The original repository exposes:

- a `Vasarhelyi` swarm module,
- an `evaluation_0` evaluation module,
- and multiple released `params_for_parallel` parameter sets.

This task directly uses those public case parameters as the benchmark input source, and reimplements the core control law and evaluation logic in Python for unified execution inside `Frontier-Engineering`.

## Input

For each case, the evaluator calls:

```python
solve(problem)
```

with the following structure:

```python
{
  "case_id": str,
  "baseline_params": dict[str, float],
  "global_config": dict[str, Any],
}
```

Where:

- `case_id` identifies the current CoFlyers case,
- `baseline_params` contains the original released parameter set for that case,
- `global_config` contains extracted simulator constants such as swarm size, simulation horizon, map bounds, point-mass model parameters, and `evaluation_0` parameters.

## Output

The candidate must return a dictionary. The recommended format is:

```python
{
  "params": {
    "r_rep_0": float,
    "p_rep": float,
    "r_frict_0": float,
    "c_frict": float,
    "v_frict": float,
    "p_frict": float,
    "a_frict": float,
    "r_shill_0": float,
    "v_shill": float,
    "p_shill": float,
    "a_shill": float,
  }
}
```

Returning a direct parameter-update dictionary is also allowed. Any parameter not explicitly provided keeps its current case baseline value.

## Evaluation Procedure

For each case, the evaluator:

1. reconstructs the initial swarm layout and global constants from the extracted CoFlyers configuration,
2. applies a Python reimplementation of the `Vasarhelyi` control law,
3. updates the swarm state using point-mass dynamics,
4. computes the CoFlyers-style `evaluation_0` metrics:
   - `phi_corr`
   - `phi_vel`
   - `phi_coll`
   - `phi_wall`
   - `phi_mnd`
5. aggregates the per-case result and averages across all released cases to obtain `combined_score`.

## Metrics

The evaluator reports:

- `combined_score`: main benchmark score, higher is better
- `mean_original_fitness`: mean value under the original CoFlyers fitness formulation
- `mean_phi_corr`: mean velocity-direction consistency
- `mean_phi_vel`: mean speed relative to the flocking target speed
- `mean_phi_coll`: mean collision ratio
- `mean_phi_wall`: mean wall-contact / out-of-bound ratio
- `mean_phi_mnd`: mean minimum-neighbor-distance penalty term
- `worst_min_pairwise_distance`: worst minimum inter-agent distance across all cases

## Constraints

- Only the released `Vasarhelyi` parameter set may be tuned
- The evaluator, original case data, and `frontier_eval` metadata must remain unchanged
- The candidate must stay executable, deterministic, and schema-compatible

## Note

This task faithfully uses the publicly released CoFlyers case parameters, but the execution backend is a **Python reimplementation**, not the original MATLAB/Simulink runtime itself.


