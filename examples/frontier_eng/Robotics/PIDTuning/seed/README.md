# PID Tuning

Tune a cascaded PID controller for a 2D quadrotor across multiple flight scenarios.
This benchmark scores candidate gain sets by tracking quality and feasibility under the provided simulator dynamics.

## File Structure

```text
PIDTuning/
├── README.md
├── Task.md
├── references/
│   └── pid_config.json
├── scripts/
│   └── init.py
└── verification/
    ├── evaluator.py
    └── requirements.txt
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r verification/requirements.txt
```

### 2. Run the Baseline Optimizer

```bash
cd benchmarks/Robotics/PIDTuning
python scripts/init.py
# Outputs: submission.json
```

### 3. Evaluate a Submission

```bash
cd benchmarks/Robotics/PIDTuning
python verification/evaluator.py --submission submission.json
```

### 4. Evaluate a Candidate Program Directly

```bash
cd benchmarks/Robotics/PIDTuning
python verification/evaluator.py scripts/init.py
```

## Submission Format

Write `submission.json` containing 12 scalar gains:

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

## Task Summary

- **System**: 2D planar quadrotor
- **State**: `[x, z, theta, x_dot, z_dot, theta_dot]`
- **Control structure**:
  - altitude PID
  - horizontal PID
  - pitch PID
- **Scenarios**: defined in `references/pid_config.json`
- **Simulation step**: `dt = 0.005 s`
- **Motor dynamics**: first-order lag
- **Hard feasibility conditions**:
  - all gains must lie inside configured bounds
  - pitch angle must remain within `max_pitch_rad`
  - each scenario must remain feasible for the entire rollout

## Scoring

- Each scenario produces an ITAE-like tracking cost.
- The final score is the geometric mean of `1 / ITAE` over all scenarios.
- Higher is better.
- If any scenario is infeasible, or any ITAE is non-positive, the final score is `0.0`.

## Run with frontier_eval (unified)

Unified benchmark: `task=unified task.benchmark=Robotics/PIDTuning`

```bash
python -m frontier_eval \
task=unified task.benchmark=Robotics/PIDTuning \
algorithm.iterations=10
```

Backwards-compatible alias (routes to the same unified benchmark via config): `task=pid_tuning`.
