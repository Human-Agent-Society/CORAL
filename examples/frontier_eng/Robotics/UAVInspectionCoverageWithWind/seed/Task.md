# UAV Inspection Coverage With Wind

## 1. Background

In industrial inspection and infrastructure monitoring, UAVs must cover distributed inspection points while handling wind disturbance and strict safety constraints.

## 2. Dynamics

Fixed-step simulation (`dt` from `scenarios.json`):

- State: `s = (x, y, z, vx, vy, vz)`
- Control: `u = (ax, ay, az)`

Update:

```text
v_{k+1} = v_k + u_k * dt
p_{k+1} = p_k + (v_{k+1} + w(p_k, t_k)) * dt
```

`w(p, t)` is scenario-specific wind velocity.

## 3. Input Scenarios

`references/scenarios.json` provides 4 fixed scenes. Each scene includes:

- 3D bounds `[xmin, xmax, ymin, ymax, zmin, zmax]`
- no-fly zones (axis-aligned boxes)
- dynamic obstacles (piecewise-linear center trajectory + radius)
- inspection points
- wind parameters
- UAV limits (`v_max`, `a_max`)
- start state
- `T_max`

## 4. Submission

`submission.json`:

```json
{
  "scenarios": [
    {
      "id": "scene_1",
      "timestamps": [0.0, 0.1, ...],
      "controls": [[ax0, ay0, az0], [ax1, ay1, az1], ...]
    }
  ]
}
```

Rules:

- `timestamps` strictly increasing and start at `0.0`
- `len(timestamps) == len(controls)`
- each control is length 3

## 5. Constraints (hard)

A scene fails on any of:

1. out-of-bounds
2. entering no-fly zone
3. collision with dynamic obstacles
4. speed limit violation (`||v|| > v_max`)
5. acceleration limit violation (`||u|| > a_max`)
6. invalid submission format

## 6. Objective and Score

- Coverage of inspection points:
  - a point is covered if UAV comes within `coverage_radius`.
- Scene score:

```text
scene_score = coverage_ratio * 100.0 - energy * 0.5
energy = sum(||u_k||^2 * dt)
```

- Final score: average `scene_score` across all scenes.
- Feasibility: all scenes must succeed; otherwise `score = null`.

## 7. Evaluator Output

```json
{
  "score": 28.85,
  "feasible": true,
  "details": {
    "scene_1": {
      "success": true,
      "coverage_ratio": 0.5,
      "energy": 30.23,
      "scene_score": 34.88
    }
  }
}
```
