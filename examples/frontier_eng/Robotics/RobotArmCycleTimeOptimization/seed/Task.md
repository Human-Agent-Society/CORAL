# Robot Arm Cycle Time Optimization

## 1. Background

In production-line pick-and-place, reducing cycle time while respecting robot hardware constraints directly increases throughput.

## 2. Task Setup

- Robot: 7-DOF KUKA LBR iiwa (`kuka_iiwa/model.urdf` from `pybullet_data`)
- Start joint vector:

```
q_start = [0.0, 0.5, 0.0, -1.5, 0.0, 1.0, 0.0]
```

- Goal joint vector:

```
q_goal = [1.2, -0.3, 0.8, -0.8, 0.5, 0.8, 1.0]
```

- Obstacle: axis-aligned box
  - center: `[0.45, -0.35, 0.65]`
  - half extents: `[0.08, 0.20, 0.08]`

## 3. Objective

Minimize total motion time `T`.

## 4. Constraints

1. Start and goal must match (`0.01 rad` tolerance).
2. Joint positions must stay within URDF limits.
3. Joint velocity limits:

```
[1.48, 1.48, 1.74, 1.74, 2.27, 2.27, 2.27] rad/s
```

4. Joint acceleration limits:

```
[3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0] rad/s^2
```

5. No robot-obstacle collision (PyBullet contact query).

## 5. Submission Format

Write `submission.json`:

```json
{
  "waypoints": [[...7 values...], [...], ...],
  "timestamps": [0.0, ..., T]
}
```

- `waypoints` shape is `(N, 7)`, `N >= 2`
- `timestamps` must be strictly increasing
- `timestamps[0] == 0.0`

## 6. Evaluation

`verification/evaluator.py`:

1. Validates format and boundary constraints.
2. Builds cubic spline interpolation over waypoints.
3. Samples each segment at 30 points.
4. Checks position/velocity/acceleration constraints.
5. Resets URDF joints in PyBullet and checks collision with obstacle.
6. Returns:
   - feasible: score = `T`
   - infeasible: score = `+inf`

Lower is better.
