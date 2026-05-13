# Fiber F1: WDM Channel + Power Allocation

## Background

A WDM system provides multiple fixed wavelength-grid channels over the same fiber.
For each traffic request (user), the scheduler must decide:

1. Which channel to use
2. How much launch power to allocate per channel

This directly affects BER/SNR, achievable data rate, and spectral utilization.

## Editable target

- `baseline/init.py`
- Function: `allocate_wdm(...)`

Only this policy function is expected to evolve.

## Structure

- `baseline/init.py`: simple sequential-assignment + equal-power baseline
- `verification/oracle.py`: stronger non-editable reference strategy (`auto/hybrid_scipy/heuristic`)
- `verification/run_validation.py`: validity checks, scoring, comparison, and plots
- `Task.md`: full task definition

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

- `scipy` (needed when using `--oracle-mode hybrid_scipy`; `auto` falls back if unavailable)

## Run

```bash
python \
  benchmarks/Optics/fiber_wdm_channel_power_allocation/verification/run_validation.py
```

Outputs:

- `verification/outputs/summary.json`
- `verification/outputs/task1_verification.png`
