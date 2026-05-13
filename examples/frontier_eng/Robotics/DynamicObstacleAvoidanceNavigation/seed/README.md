# Dynamic Obstacle Avoidance Navigation

Navigate a differential-drive robot from start to goal in 2D environments with static and dynamic obstacles.

## File Structure

```
DynamicObstacleAvoidanceNavigation/
├── README.md
├── README_zh-CN.md
├── Task.md
├── Task_zh-CN.md
├── references/
│   └── scenarios.json
├── verification/
│   ├── evaluator.py
│   └── requirements.txt
└── baseline/
    ├── solution.py
    └── result_log.txt
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r verification/requirements.txt
```

### 2. Generate Baseline Submission

```bash
python baseline/solution.py
# Outputs: submission.json
```

### 3. Evaluate

```bash
python verification/evaluator.py --submission submission.json
# Outputs: {"score": <float|null>, "feasible": <bool>, "details": {...}}
```

## Submission Format

`submission.json`:

```json
{
  "scenarios": [
    {
      "id": "scene_1",
      "timestamps": [0.0, 0.2, 0.4],
      "controls": [[0.0, 0.0], [0.7, 0.4], [0.8, 0.2]]
    }
  ]
}
```

## Scoring

- All 3 scenes must be successful to be feasible.
- Score = average arrival time across all scenes (lower is better).
- Any violation (collision, out-of-bounds, limit violation, timeout) makes that scene fail.
- If any scene fails, final `feasible=false` and `score=null`.

## Run with frontier_eval (unified)

Unified benchmark: `task=unified task.benchmark=Robotics/DynamicObstacleAvoidanceNavigation`

```bash
python -m frontier_eval task=unified task.benchmark=Robotics/DynamicObstacleAvoidanceNavigation algorithm.iterations=0
```

Backwards-compatible alias (routes to the same unified benchmark via config): `task=dynamic_obstacle_navigation`.
