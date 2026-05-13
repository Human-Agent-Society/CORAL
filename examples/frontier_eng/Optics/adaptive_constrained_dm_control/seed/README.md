# Adaptive A1: Constrained DM Control

This task focuses on single-step constrained control for deformable mirror (DM) commands.

## Why this task matters

A common AO control law is `u = R @ s`.
In real hardware, actuator voltage must stay within bounds.
So a simple "solve first, then clip" strategy is usually suboptimal.

This task asks the agent to improve correction quality under strict voltage limits.

## Folder Structure

```text
task1_constrained_dm_control/
  baseline/
    init.py                        # editable target for the agent
  verification/
    evaluate.py                    # validity checks + baseline/reference comparison
    reference_controller.py        # stronger reference implementation
    outputs/                       # generated after running evaluate.py
  README.md
  README_zh-CN.md
  Task.md
  Task_zh-CN.md
```

## Environment Dependencies

`pip install -r benchmarks/Optics/requirements.txt`

## How to Run

```bash
cd benchmarks/Optics/adaptive_constrained_dm_control
python verification/evaluate.py
```

Use a custom candidate module:

```bash
python verification/evaluate.py \
  --candidate /path/to/your/solution.py
```

## Outputs

- `verification/outputs/metrics.json`
- `verification/outputs/metrics_comparison.png`
- `verification/outputs/example_visualization.png`

`metrics.json` compares candidate baseline and reference under the same random seeds and scenarios.
