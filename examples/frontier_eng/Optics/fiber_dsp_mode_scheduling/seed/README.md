# Fiber F3: DSP Mode Scheduling (EDC vs DBP)

## Background

Receiver DSP can run in different compensation modes:

- EDC: lower latency, lower nonlinear compensation gain
- DBP: higher latency, usually better quality

Under a global latency budget, scheduling DBP on all users is often impossible.

## Editable target

- `baseline/init.py`
- Function: `choose_dsp_mode(...)`

## Structure

- `baseline/init.py`: low-SNR-first DBP baseline
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
  benchmarks/Optics/fiber_dsp_mode_scheduling/verification/run_validation.py
```

Outputs:

- `verification/outputs/summary.json`
- `verification/outputs/task3_verification.png`
