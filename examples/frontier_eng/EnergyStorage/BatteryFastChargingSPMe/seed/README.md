# BatteryFastChargingSPMe

Navigation document for this task.

## Goal

Design a staged fast-charging policy for a lithium-ion cell using a reduced electrochemical-thermal-aging model inspired by `SPMe-T-Aging`.

Compared with `BatteryFastChargingProfile`, this task includes:

- separate positive / negative solid-state surface dynamics,
- electrolyte polarization dynamics,
- Butler-Volmer-style kinetic overpotential proxies,
- thermal coupling,
- plating-margin and SEI-aging surrogates with clearer physical meaning.

## Files

- `Task.md`: task contract and scoring rules.
- `Task_zh-CN.md`: Chinese version of the task contract.
- `references/README.md`: English modeling notes.
- `references/README_zh-CN.md`: Chinese modeling notes.
- `references/battery_config.json`: battery, model, and scoring parameters.
- `scripts/init.py`: minimal runnable starter and initial candidate.
- `baseline/solution.py`: baseline staged charging policy.
- `verification/evaluator.py`: evaluator entry.
- `verification/requirements.txt`: local evaluator dependencies.
- `verification/docker/Dockerfile`: optional containerized evaluator.
- `frontier_eval/`: unified-task metadata for `python -m frontier_eval`.

## Environment

From repository root:

```bash
pip install -r frontier_eval/requirements.txt
pip install -r benchmarks/EnergyStorage/BatteryFastChargingSPMe/verification/requirements.txt
```

## Quick Run

Run from repository root:

```bash
python benchmarks/EnergyStorage/BatteryFastChargingSPMe/verification/evaluator.py \
  benchmarks/EnergyStorage/BatteryFastChargingSPMe/scripts/init.py
```

Or run from the task directory:

```bash
cd benchmarks/EnergyStorage/BatteryFastChargingSPMe
python verification/evaluator.py scripts/init.py
```

To test with an explicit parameter file:

```bash
python verification/evaluator.py scripts/init.py --config references/battery_config.json
```

## frontier_eval Task Name

This task uses the unified task framework. Run with:

```bash
python -m frontier_eval task=battery_fast_charging_spme algorithm.iterations=0
```

Equivalent explicit unified command:

```bash
python -m frontier_eval \
  task=unified \
  task.benchmark=EnergyStorage/BatteryFastChargingSPMe \
  algorithm.iterations=0
```
