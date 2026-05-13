# Dynamic Obstacle Avoidance Navigation

## 1. Background

Mobile robots in warehouses, factories, and hospitals must move quickly while safely avoiding moving objects (workers, carts, AGVs).

## 2. Task Definition

For each fixed scenario, control a differential-drive robot from start to goal under kinematic limits.

### 2.1 Robot Motion Model

At simulation step `dt = 0.05 s`:

```
x_{k+1} = x_k + v_k * cos(theta_k) * dt
y_{k+1} = y_k + v_k * sin(theta_k) * dt
theta_{k+1} = theta_k + omega_k * dt
```

### 2.2 Inputs

`references/scenarios.json` contains 3 fixed scenarios. Each scenario includes:

- map bounds
- static obstacles (circles/rectangles)
- dynamic obstacles with piecewise-linear time trajectories
- robot limits (`radius`, `v_max`, `omega_max`, `a_max`)
- start state and goal point
- max time `T_max`

## 3. Submission Format

Submit `submission.json`:

```json
{
  "scenarios": [
    {
      "id": "scene_1",
      "timestamps": [0.0, 0.2, ...],
      "controls": [[v0, w0], [v1, w1], ...]
    }
  ]
}
```

Rules:

- `timestamps` strictly increasing and start at `0.0`
- `len(controls) == len(timestamps)`
- controls must satisfy speed/turn-rate limits
- adjacent controls must satisfy acceleration limit

## 4. Constraints

A scene fails if any of the following happens:

1. collision with static or dynamic obstacles
2. robot goes out of map bounds
3. control limits violated
4. cannot reach goal before `T_max`

Goal is reached when `distance(robot, goal) <= goal_tolerance`.

## 5. Objective and Score

- Objective: minimize arrival time.
- Feasible only if all 3 scenes succeed.
- Score (feasible case): average arrival time over 3 scenes.
- Infeasible case: `score = null`, `feasible = false`.

## 6. Evaluator Output

`verification/evaluator.py` outputs JSON:

```json
{
  "score": 8.4,
  "feasible": true,
  "details": {
    "scene_1": {"success": true, "time": 7.9},
    "scene_2": {"success": true, "time": 8.6},
    "scene_3": {"success": true, "time": 8.7}
  }
}
```
