# Adaptive A4: Fault-Tolerant Sensor Fusion

This task focuses on robust control under multi-sensor corruption.

## Why this task matters

In multi-WFS systems, one channel can be mis-calibrated or noisy.
Naively averaging all sensors can propagate outliers directly into DM commands.

This task asks the agent to fuse multi-sensor slopes robustly before control.

## Folder Structure

```text
task4_fault_tolerant_fusion/
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
- Task-specific oracle dependency: `scikit-learn` (used by `verification/reference_controller.py`, `sklearn.ensemble.IsolationForest`)
- Recommended one-shot install from repo root: `python -m pip install -r benchmarks/Optics/requirements.txt`

## Run

```bash
cd benchmarks/Optics/adaptive_fault_tolerant_fusion
python verification/evaluate.py
```

## Outputs

- `verification/outputs/metrics.json`
- `verification/outputs/metrics_comparison.png`
- `verification/outputs/example_visualization.png`
