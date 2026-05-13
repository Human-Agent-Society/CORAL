# Adaptive A2: Temporal Smooth Control

This task targets **time-series AO control** with command smoothness requirements.

## Why this task matters

In real systems, command jitter can be harmful:
- actuator wear,
- mirror vibration,
- unstable loop behavior.

Pure frame-wise control may minimize instantaneous residual, but produce noisy command trajectories.

This task optimizes a practical objective that balances correction quality and command smoothness.

## Folder Structure

```text
task2_temporal_smooth_control/
  baseline/
    init.py
  verification/
    evaluate.py
    reference_controller.py
    outputs/
  README.md
  README_zh-CN.md
  Task.md
  Task_zh-CN.md
```

## Environment Dependencies

- Python: `3.10+` (tested with `python`)
- Baseline candidate runtime: `numpy`
- Verification runtime: `numpy`, `matplotlib`, local `aotools` package (this repository)
- Task-specific oracle dependency: none (reference is analytical and does not require extra third-party solver)
- Recommended one-shot install from repo root: `python -m pip install -r benchmarks/Optics/requirements.txt`

## How to Run

```bash
cd benchmarks/Optics/adaptive_temporal_smooth_control
python verification/evaluate.py
```

## Outputs

- `verification/outputs/metrics.json`
- `verification/outputs/metrics_comparison.png`
- `verification/outputs/example_visualization.png`
