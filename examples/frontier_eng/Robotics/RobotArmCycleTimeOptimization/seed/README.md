# Robot Arm Cycle Time Optimization

Minimize the motion time of a 7-DOF KUKA LBR iiwa arm moving from a start to a goal configuration, collision-free.

## File Structure

```
RobotArmCycleTimeOptimization/
├── Task.md                    # Full task specification
├── Task_zh-CN.md              # Task spec (Chinese)
├── references/
│   └── robot_config.json      # Joint limits, obstacle definition
├── verification/
│   ├── evaluator.py           # PyBullet + URDF scoring script
│   ├── requirements.txt       # Python dependencies
│   └── docker/
│       └── Dockerfile
└── baseline/
    └── solution.py            # Time-scaling baseline with via-point
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r verification/requirements.txt
```

### 2. Run the Baseline

```bash
python baseline/solution.py
# Outputs: submission.json
```

### 3. Evaluate

```bash
python verification/evaluator.py --submission submission.json
# Outputs: {"score": <T in seconds>, "feasible": true/false}
```

### 4. Docker Evaluation

```bash
cd verification
docker build -t arm-eval -f docker/Dockerfile .
docker run --rm -v $(pwd)/../submission.json:/workspace/submission.json arm-eval
```

## Submission Format

`submission.json`:

```json
{
  "waypoints": [
    [0.0,  0.5,  0.0, -1.5, 0.0, 1.0, 0.0],
    [0.3,  0.1,  0.4, -1.1, 0.2, 0.9, 0.5],
    [1.2, -0.3,  0.8, -0.8, 0.5, 0.8, 1.0]
  ],
  "timestamps": [0.0, 1.2, 2.5]
}
```

## Scoring

| Result | Score |
|--------|-------|
| Feasible trajectory | `T` seconds (lower is better) |
| Any constraint violated | `+inf` (infeasible) |

## Task Summary

- **Robot**: KUKA LBR iiwa (URDF via `pybullet_data`)
- **Start**: `[0.0, 0.5, 0.0, -1.5, 0.0, 1.0, 0.0]` rad
- **Goal**: `[1.2, -0.3, 0.8, -0.8, 0.5, 0.8, 1.0]` rad
- **Obstacle**: AABB at center `[0.45, -0.35, 0.65]`, half-extents `[0.08, 0.20, 0.08]` m
- **Objective**: Minimize total time `T`

## Run with frontier_eval (unified)

Unified benchmark: `task=unified task.benchmark=Robotics/RobotArmCycleTimeOptimization`

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=Robotics/RobotArmCycleTimeOptimization task.runtime.env_name=frontier-v1-main algorithm.iterations=0
```

Backwards-compatible alias (routes to the same unified benchmark via config): `task=robot_arm_cycle_time`.
