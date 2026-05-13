# Fiber F4: Spectrum Packing with Guard Bands

## Background

Users request different bandwidth sizes (in spectrum slots). The scheduler must pack those requests into finite slots while preserving guard bands between neighbors.

This impacts:

- blocking/acceptance ratio
- spectral utilization
- fragmentation
- adjacent-channel interference risk (modeled via BER proxy)

## Editable target

- `baseline/init.py`
- Function: `pack_spectrum(...)`

## Structure

- `baseline/init.py`: first-fit decreasing baseline
- `verification/oracle.py`: stronger reference (`auto/hybrid/exact_geometry/heuristic`)
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

- `ortools` (needed for `--oracle-mode exact_geometry`; `auto` falls back to heuristic/hybrid if unavailable)

## Run

```bash
python \
  benchmarks/Optics/fiber_guardband_spectrum_packing/verification/run_validation.py
```

Outputs:

- `verification/outputs/summary.json`
- `verification/outputs/task4_verification.png`
