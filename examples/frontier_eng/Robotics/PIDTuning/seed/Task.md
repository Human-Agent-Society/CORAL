# PID Tuning

## 1. Problem

Tune 12 gains of a cascaded PID controller for a 2D quadrotor.
The controller must stabilize and track waypoint targets across multiple scenarios with different starts, targets, durations, and wind disturbances.

## 2. Dynamics and Controller

The simulator state is:

```text
[x, z, theta, x_dot, z_dot, theta_dot]
```

The evaluator uses:

- total thrust `T`
- torque `tau`
- first-order motor lag
- linear drag and angular drag

The controller has three PID loops:

1. **Altitude loop**: controls vertical motion
2. **Horizontal loop**: converts horizontal error into desired pitch
3. **Pitch loop**: tracks desired pitch with torque

Derivative terms use filtered derivatives with parameters `N_z`, `N_x`, and `N_theta`.

## 3. Decision Variables

Submit the following 12 gains:

- `Kp_z`, `Ki_z`, `Kd_z`, `N_z`
- `Kp_x`, `Ki_x`, `Kd_x`, `N_x`
- `Kp_theta`, `Ki_theta`, `Kd_theta`, `N_theta`

Each value must stay within the bounds in `references/pid_config.json`.

## 4. Scenarios

The current configuration contains 4 scenarios:

1. `vertical_hover`
2. `lateral_move`
3. `combined_wind`
4. `multi_waypoint`

Each scenario specifies:

- start position
- waypoint list
- rollout duration
- constant wind disturbance

## 5. Submission Format

Write `submission.json` in the working directory:

```json
{
  "Kp_z": 8.0,
  "Ki_z": 0.5,
  "Kd_z": 4.0,
  "N_z": 20.0,
  "Kp_x": 0.1,
  "Ki_x": 0.01,
  "Kd_x": 0.1,
  "N_x": 10.0,
  "Kp_theta": 10.0,
  "Ki_theta": 0.5,
  "Kd_theta": 3.0,
  "N_theta": 20.0
}
```

All keys are required and must be numeric.

## 6. Feasibility Rules

A submission is infeasible if any of the following occurs:

1. a required key is missing
2. a gain is not numeric
3. a gain is outside its configured range
4. any scenario violates the pitch limit
5. any scenario produces non-positive ITAE

Infeasible submissions receive score `0.0`.

## 7. Objective

Minimize tracking error over time across all scenarios.
The evaluator computes, for each scenario, an ITAE-style quantity:

```text
ITAE = ∫ t * position_error(t) dt
```

It then returns:

```text
score = geometric_mean(1 / ITAE_i)
```

Higher score is better.

## 8. Evaluation

### Evaluate a produced submission

```bash
python verification/evaluator.py --submission submission.json
```

### Run a candidate optimizer script and evaluate its output

```bash
python verification/evaluator.py scripts/init.py
```

## 9. References

- Configuration: `references/pid_config.json`
- Baseline optimizer: `scripts/init.py`
- Evaluator: `verification/evaluator.py`
