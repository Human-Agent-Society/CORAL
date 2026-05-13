# UAV Inspection Coverage With Wind

Optimize a UAV control sequence to maximize inspection coverage under wind disturbance, while respecting hard safety and kinematic constraints (including dynamic-obstacle avoidance).

## File Structure

```text
UAVInspectionCoverageWithWind/
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

1. Install dependencies:

```bash
pip install -r verification/requirements.txt
```

2. Generate baseline submission:

```bash
python baseline/solution.py
```

3. Evaluate:

```bash
python verification/evaluator.py --submission submission.json
```

Evaluator output:

```json
{
  "score": 28.85,
  "feasible": true,
  "details": {
    "scene_1": {"success": true, "coverage_ratio": 0.5, "energy": 30.23, "scene_score": 34.88}
  }
}
```

## Submission Format

`submission.json`:

```json
{
  "scenarios": [
    {
      "id": "scene_1",
      "timestamps": [0.0, 0.1, 0.2],
      "controls": [[0.0, 0.0, 0.0], [0.3, -0.1, 0.0], [0.2, 0.0, 0.1]]
    }
  ]
}
```

## Scoring

- Primary objective: maximize `coverage_ratio`.
- Tie-breaker: lower control energy.
- Per-scene score: `coverage_ratio * 100.0 - energy * 0.5`.
- Final score: average over all scenes.
- Any scene constraint violation (including dynamic-obstacle collision) => `feasible=false`, `score=null`.

## Run with frontier_eval (unified)

Unified benchmark: `task=unified task.benchmark=Robotics/UAVInspectionCoverageWithWind`

```bash
python -m frontier_eval task=unified task.benchmark=Robotics/UAVInspectionCoverageWithWind algorithm.iterations=0
```

Backwards-compatible alias (routes to the same unified benchmark via config): `task=uav_inspection_coverage`.
