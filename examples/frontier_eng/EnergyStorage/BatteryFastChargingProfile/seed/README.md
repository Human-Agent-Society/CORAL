# BatteryFastChargingProfile

Navigation document for this task.

## Goal

Design a multi-stage constant-current fast-charging policy for a lithium-ion cell from `10%` SOC to `80%` SOC.

The objective is to charge as quickly as possible while keeping:

- terminal voltage within safe limits,
- cell temperature under control,
- lithium-plating risk and aging cost low.

## Files

- `Task.md`: task contract and scoring rules.
- `Task_zh-CN.md`: Chinese version of the task contract.
- `references/README.md`: industrial context and modeling notes.
- `references/README_zh-CN.md`: Chinese modeling notes.
- `references/battery_config.json`: battery, thermal, and scoring parameters.
- `scripts/init.py`: minimal runnable starter and initial candidate.
- `baseline/solution.py`: simple baseline profile generator.
- `verification/evaluator.py`: evaluator entry.
- `verification/requirements.txt`: local evaluator dependencies.
- `verification/docker/Dockerfile`: optional containerized evaluator.
- `frontier_eval/`: unified-task metadata for `python -m frontier_eval`.

## Environment

From repository root:

```bash
pip install -r frontier_eval/requirements.txt
pip install -r benchmarks/EnergyStorage/BatteryFastChargingProfile/verification/requirements.txt
```

## Quick Run

Run from repository root:

```bash
python benchmarks/EnergyStorage/BatteryFastChargingProfile/verification/evaluator.py \
  benchmarks/EnergyStorage/BatteryFastChargingProfile/scripts/init.py
```

Or run from the task directory:

```bash
cd benchmarks/EnergyStorage/BatteryFastChargingProfile
python verification/evaluator.py scripts/init.py
```

`scripts/init.py` is expected to be runnable and should produce a feasible charging profile with non-zero `combined_score` and `valid=1.0`.

To test a different battery setup:

```bash
python verification/evaluator.py scripts/init.py --config references/battery_config.json
```

## frontier_eval Task Name

This task uses the unified task framework. Run with:

```bash
python -m frontier_eval task=battery_fast_charging_profile algorithm.iterations=0
```

Equivalent explicit unified command:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=EnergyStorage/BatteryFastChargingProfile \
  algorithm.iterations=0
```
