# Fiber F2: Joint MCS + Power Scheduling

## Background

For each user, the controller selects:

1. Modulation order (`MCS`, e.g. 4/16/64-QAM)
2. Launch power

Higher MCS improves throughput but requires better SNR and may increase BER.

## Editable target

- `baseline/init.py`
- Function: `select_mcs_power(...)`

## Structure

- `baseline/init.py`: threshold-based baseline
- `verification/oracle.py`: stronger reference (`auto/exact/heuristic`, CP-SAT + fallback DP)
- `verification/run_validation.py`: valid checks, scoring, plots
- `Task.md`: full specification

## Environment dependencies

One-command setup:

```bash
python -m pip install -r benchmarks/Optics/requirements.txt
```

Required (baseline + verification):

- Recommended interpreter: `python`
- `numpy`
- `matplotlib`
- `optic` (OptiCommPy package in this repository, used by verification for `theoryBER`)

Optional (stronger oracle mode):

- `ortools` (needed for `--oracle-mode exact`; `auto` falls back to DP if unavailable)

## Run

```bash
python \
  benchmarks/Optics/fiber_mcs_power_scheduling/verification/run_validation.py
```

Outputs:

- `verification/outputs/summary.json`
- `verification/outputs/task2_verification.png`
