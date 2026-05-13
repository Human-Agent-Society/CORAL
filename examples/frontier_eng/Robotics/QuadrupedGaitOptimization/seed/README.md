# Quadruped Gait Optimization

Maximize the forward locomotion speed of a quadruped robot by optimizing 8 gait parameters.

## File Structure

```
QuadrupedGaitOptimization/
├── Task.md
├── Task_zh-CN.md
├── references/
│   ├── gait_config.json
│   └── ant.xml
├── verification/
│   ├── evaluator.py
│   ├── requirements.txt
│   └── docker/
│       └── Dockerfile
└── baseline/
    └── solution.py
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
# Outputs: {"score": <speed m/s>, "feasible": true/false}
```

### 4. Docker Evaluation

```bash
docker build -t quad-eval -f verification/docker/Dockerfile .
docker run --rm -v $(pwd)/submission.json:/workspace/submission.json quad-eval
```

## Submission Format

`submission.json`:

```json
{
  "step_frequency": 1.8,
  "duty_factor": 0.62,
  "step_length": 0.16,
  "step_height": 0.07,
  "phase_FR": 0.5,
  "phase_RL": 0.5,
  "phase_RR": 0.0,
  "lateral_distance": 0.13
}
```

## Scoring

| Result | Score |
|--------|-------|
| Valid gait | `v` m/s (higher is better) |
| Hard constraint violated | `0.0` |

## Hard Constraints

- Roll/pitch cannot exceed configured threshold
- Actuator force cannot exceed configured limit
- Robot must make forward progress over fixed duration

## Objective

- Maximise average forward speed over a fixed MuJoCo simulation horizon

## Run with frontier_eval (unified)

Unified benchmark: `task=unified task.benchmark=Robotics/QuadrupedGaitOptimization`

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval task=unified task.benchmark=Robotics/QuadrupedGaitOptimization task.runtime.env_name=frontier-v1-main algorithm.iterations=0
```

Backwards-compatible alias (routes to the same unified benchmark via config): `task=quadruped_gait`.
